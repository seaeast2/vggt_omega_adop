"""Bounded HTTP-range ZIP reader: fetch central directory and selected members."""
import io
import json
import time
import urllib.request
import zipfile


class RangeReader(io.RawIOBase):
    def __init__(self, url, size):
        self.url = url; self.size = size; self.position = 0; self.transfers = []
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.position
    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else (self.position+offset if whence == 1 else self.size+offset)
        if self.position < 0: raise ValueError(self.position)
        return self.position
    def read(self, n=-1):
        if n < 0: n = self.size-self.position
        n = min(n, self.size-self.position)
        if n <= 0: return b''
        if n > 64*1024**2: raise ValueError(f'Refusing an unbounded request: {n}')
        start = self.position; end = start+n-1
        suffix = ('&' if '?' in self.url else '?')+f'range_request={start}-{end}'
        request = urllib.request.Request(self.url+suffix, headers={'Range': f'bytes={start}-{end}', 'User-Agent': 'UAVScenes-research-subset/1.0'})
        error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    if response.status != 206: raise RuntimeError(f'Expected HTTP 206, got {response.status}')
                    expected = f'bytes {start}-{end}/{self.size}'
                    if response.headers.get('Content-Range') != expected: raise RuntimeError('Unexpected Content-Range')
                    data = response.read(n+1)
                if len(data) != n: raise RuntimeError(f'Short range: {len(data)} vs {n}')
                self.position += n; self.transfers.append({'start': start, 'end': end, 'bytes': n}); return data
            except Exception as exc:
                error = exc
                if attempt < 2: time.sleep(1)
        raise error


def open_zip(url, size):
    reader = RangeReader(url, size)
    return reader, zipfile.ZipFile(reader)


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    p = argparse.ArgumentParser(); p.add_argument('--url', required=True); p.add_argument('--size', type=int, required=True); p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    reader, archive = open_zip(a.url, a.size)
    rows = [{'name': x.filename, 'size': x.file_size, 'compressed_size': x.compress_size, 'offset': x.header_offset, 'crc32': x.CRC} for x in archive.infolist()]
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps({'url': a.url, 'size': a.size, 'members': rows, 'transfers': reader.transfers}, indent=2)+'\n')
    print('members', len(rows), 'network bytes', sum(x['bytes'] for x in reader.transfers))
    for name in ['HKairport01', 'AMtown01']:
        subset = [x for x in rows if name in x['name']]
        print(name, 'members', len(subset)); print(json.dumps(subset[:6], indent=2))
    print('metadata examples', [x['name'] for x in rows if x['name'].endswith(('.json', '.py', '.txt', '.yaml', '.yml'))][:50])
