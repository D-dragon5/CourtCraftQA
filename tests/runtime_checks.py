"""Read-only checks against a running viewer; never sends a save request."""
import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request


def check_runtime(base):
    def get(path, headers=None):
        request = urllib.request.Request(base + path, headers=headers or {})
        return urllib.request.urlopen(request, timeout=300)

    def data(path):
        with get(path) as response:
            return json.load(response)

    health = data('/api/health')
    assert health['status'] == 'ok'
    with get('/') as response:
        html = response.read().decode('utf-8')
    assert '__CSRF_TOKEN__' not in html
    assert re.search(r'<meta\s+name="viewer-token"\s+content="[^"]+"', html)
    for path, kind in [('/static/viewer.css', 'text/css'),
                       ('/static/viewer.js', 'javascript'),
                       ('/assets/dddlong-dragon.png', 'image/png')]:
        with get(path) as response:
            assert kind in response.headers['Content-Type']
            assert len(response.read()) > 100
    try:
        get('/static/%2e%2e/config.json')
        raise AssertionError('Static path escape accepted')
    except urllib.error.HTTPError as error:
        assert error.code == 404

    rows = data('/api/videos')
    assert len(rows) == health['videos'] and rows
    reference_count = 0
    reference_rows = 0
    for row in rows:
        reference = data('/api/references?path=' + urllib.parse.quote(row['path']))
        assert not reference.get('error'), row['path']
        reference_count += 1
        reference_rows += len(reference['records'])

    media_checked = []
    for extension in ['.mp4', '.mov']:
        row = next((row for row in rows if row['path'].lower().endswith(extension)), None)
        if row is None:
            continue
        query = urllib.parse.quote(row['path'])
        attachments = data('/api/assets?path=' + query)
        assert attachments['images'] and attachments['json']
        document = data('/api/json?path=' + urllib.parse.quote(attachments['json'][0]['path']))
        assert document['source_available'] and document['source_version']
        assert isinstance(json.loads(document['text']), dict)
        assert isinstance(json.loads(document['source_text']), dict)
        prepared = data('/api/prepare?path=' + query)
        with get(prepared['url'], {'Range': 'bytes=0-1023'}) as response:
            assert response.status == 206
            assert len(response.read()) == 1024
        image_path = '/image?path=' + urllib.parse.quote(attachments['images'][0]['path'])
        with get(image_path) as response:
            assert response.headers['Content-Type'].startswith('image/')
            assert len(response.read()) > 100
        media_checked.append(row['path'])

    summary = {'status': 'passed', 'videos': len(rows), 'excel_files': reference_count,
               'excel_records': reference_rows, 'media_checked': media_checked,
               'static_assets': 'passed', 'source_and_annotations_read': 'passed',
               'static_path_escape': 'rejected', 'data_root': health['data_root']}
    print(json.dumps(summary, ensure_ascii=False))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base_url', nargs='?', default='http://127.0.0.1:5014')
    check_runtime(parser.parse_args().base_url.rstrip('/'))
