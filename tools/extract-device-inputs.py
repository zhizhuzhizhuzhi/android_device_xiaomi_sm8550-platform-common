#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Populate device-owned inputs from local dumps with pinned hash verification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import importlib.util


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def elf_section(data, name):
    if data[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Expected a little-endian ELF64 input')
    offset = struct.unpack_from('<Q', data, 40)[0]
    size, count, strings_index = struct.unpack_from('<HHH', data, 58)
    headers = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i * size) for i in range(count)]
    strings = headers[strings_index]
    names = data[strings[4]:strings[4] + strings[5]]
    for header in headers:
        if names[header[0]:].split(b'\0', 1)[0].decode() == name:
            return data[header[4]:header[4] + header[5]]
    raise ValueError('Missing ELF section ' + name)


def patch_elf(path, recipe, patchelf):
    before = path.read_bytes()
    if recipe.get('replace_needed'):
        if not patchelf:
            raise ValueError('Provide --patchelf pointing to pinned patchelf 0.17.2')
        if recipe.get('patchelf_sha256') and sha(patchelf) != recipe['patchelf_sha256']:
            raise ValueError('patchelf executable differs from the recorded build tool')
        subprocess.run([str(patchelf), '--replace-needed', *recipe['replace_needed'], str(path)], check=True)
        if elf_section(before, '.text') != elf_section(path.read_bytes(), '.text'):
            raise ValueError('DT_NEEDED fix unexpectedly changed machine code')
    if recipe.get('byte_patches'):
        data = bytearray(path.read_bytes())
        expected = recipe.get('before_byte_patches_sha256')
        if expected and hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Unexpected intermediate ELF hash')
        for patch in recipe['byte_patches']:
            address = int(patch['address'], 0)
            offset = None
            phoff = struct.unpack_from('<Q', data, 32)[0]
            phsize, phcount = struct.unpack_from('<HH', data, 54)
            for i in range(phcount):
                header = struct.unpack_from('<IIQQQQQQ', data, phoff + i * phsize)
                if header[0] == 1 and header[3] <= address < header[3] + header[5]:
                    offset = header[2] + address - header[3]
                    break
            if offset is None:
                raise ValueError('Patch address is not file-backed: ' + patch['address'])
            old, new = bytes.fromhex(patch['old']), bytes.fromhex(patch['new'])
            if len(old) != len(new) or data[offset:offset + len(old)] != old:
                raise ValueError('Instruction precondition failed: ' + patch['address'])
            data[offset:offset + len(new)] = new
        path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', type=Path, required=True, help='Android checkout root')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--source', type=Path, action='append', default=[], help='Local partition dump, prepared kernel payload, or matching input root; repeatable')
    parser.add_argument('--patchelf', type=Path)
    parser.add_argument('--built-capslock', type=Path, help='Explicitly use a locally rebuilt, ABI-validated Caps Lock module')
    parser.add_argument('--verify', action='store_true', help='Check installed inputs without writing')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    root = args.tree.resolve()
    spec = json.loads(args.manifest.read_text())
    results, missing = [], []
    # Resolve only named candidates; no recursive source-directory search.
    files = list(spec['files'])
    for include in spec.get('includes', []):
        included = (args.manifest.parent / include).resolve()
        if not included.is_relative_to(root):
            raise ValueError('Input manifest escapes checkout')
        files.extend(json.loads(included.read_text())['files'])
    destinations = [row['destination'] for row in files]
    if len(destinations) != len(set(destinations)):
        raise ValueError('Duplicate input destination')
    for row in files:
        relative = Path(row['destination'])
        target = (root / relative).resolve()
        if relative.is_absolute() or '..' in relative.parts or not target.is_relative_to(root):
            raise ValueError('Unsafe destination')
        if args.built_capslock and str(relative).replace('\\', '/') == 'device/xiaomi/sheng/kernel/prebuilt/vendor_dlkm/hid-nanosic-capslock.ko':
            verifier_path = args.manifest.resolve().parent / 'keyboard/verify-built-module.py'
            module_spec = importlib.util.spec_from_file_location('capslock_verifier', verifier_path)
            verifier = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(verifier)
            proof = verifier.validate(args.built_capslock)
            if args.verify:
                if not target.is_file() or sha(target) != proof['sha256']:
                    raise ValueError('Installed Caps Lock module differs from explicit rebuilt module')
            elif not target.is_file() or sha(target) != proof['sha256']:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name('.hid-nanosic-capslock.ko.built')
                if temporary.exists():
                    raise ValueError('Unfinished module install exists')
                shutil.copyfile(args.built_capslock, temporary)
                temporary.chmod(0o644)
                os.replace(temporary, target)
            results.append({'path': str(relative), 'stage': 'rebuilt_module', **proof})
            continue
        if target.exists():
            if not target.is_file() or sha(target) != row['sha256']:
                raise ValueError('Refusing to replace a different existing input: ' + str(relative))
            results.append({'path': str(relative), 'stage': 'verified'})
            continue
        if args.verify:
            missing.append(str(relative))
            continue
        source = None
        apply_recipe = False
        for folder in args.source:
            for candidate in row['sources']:
                path = (folder.resolve() / candidate).resolve()
                if not path.is_relative_to(folder.resolve()) or not path.is_file():
                    continue
                actual = sha(path)
                if actual == row['sha256']:
                    source = path
                    break
                if row.get('recipe') and actual == row['recipe']['input_sha256']:
                    source, apply_recipe = path, True
                    break
            if source:
                break
        if source is None:
            missing.append(str(relative))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix='.extract-', dir=target.parent)
        os.close(handle)
        temporary = Path(temporary)
        try:
            shutil.copyfile(source, temporary)
            if apply_recipe:
                patch_elf(temporary, row['recipe'], args.patchelf)
            if sha(temporary) != row['sha256']:
                raise ValueError('Generated input hash mismatch: ' + str(relative))
            temporary.chmod(row.get('mode', 0o644))
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        results.append({'path': str(relative), 'stage': 'generated' if apply_recipe else 'copied'})
    report = {'verified': len(results), 'missing': missing, 'files': results}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'verified': len(results), 'missing_count': len(missing), 'missing': missing[:20]}, indent=2))
    if missing:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
