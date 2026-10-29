"""Upload the App Store screenshots (iPhone 6.9") to the version being prepared in App Store Connect.

Runs in the Codemagic workflow ios-screenshots, which provides the App Store Connect API key as
APP_STORE_CONNECT_ISSUER_ID / APP_STORE_CONNECT_KEY_IDENTIFIER / APP_STORE_CONNECT_PRIVATE_KEY.
It only changes the screenshots: it never submits anything for review.

    python3 store/upload_screenshots.py <app id> <folder with the .png files>
"""
import glob
import hashlib
import os
import sys
import time

import jwt
import requests

API = 'https://api.appstoreconnect.apple.com/v1'
DISPLAY_TYPE = 'APP_IPHONE_67'  # the "iPhone 6.9-inch Display" slot


def token():
    now = int(time.time())
    return jwt.encode(
        {'iss': os.environ['APP_STORE_CONNECT_ISSUER_ID'], 'iat': now, 'exp': now + 15 * 60, 'aud': 'appstoreconnect-v1'},
        os.environ['APP_STORE_CONNECT_PRIVATE_KEY'],
        algorithm='ES256',
        headers={'kid': os.environ['APP_STORE_CONNECT_KEY_IDENTIFIER']},
    )


def call(method, path, **kwargs):
    url = path if path.startswith('http') else API + path
    r = requests.request(method, url, headers={'Authorization': f'Bearer {token()}'}, timeout=60, **kwargs)
    if r.status_code >= 400:
        sys.exit(f'{method} {path} failed: {r.status_code} {r.text}')
    return r.json() if r.content else {}


def editable_version(app_id):
    versions = call('GET', f'/apps/{app_id}/appStoreVersions', params={'filter[platform]': 'IOS', 'limit': 20})['data']
    for v in versions:
        if v['attributes']['appStoreState'] in ('PREPARE_FOR_SUBMISSION', 'DEVELOPER_REJECTED', 'REJECTED', 'METADATA_REJECTED'):
            return v
    sys.exit('No App Store version is open for editing (Prepare for Submission).')


def screenshot_set(localization_id):
    sets = call('GET', f'/appStoreVersionLocalizations/{localization_id}/appScreenshotSets')['data']
    for s in sets:
        if s['attributes']['screenshotDisplayType'] == DISPLAY_TYPE:
            return s['id']
    created = call('POST', '/appScreenshotSets', json={'data': {
        'type': 'appScreenshotSets',
        'attributes': {'screenshotDisplayType': DISPLAY_TYPE},
        'relationships': {'appStoreVersionLocalization': {'data': {'type': 'appStoreVersionLocalizations', 'id': localization_id}}},
    }})
    return created['data']['id']


def upload(set_id, path):
    data = open(path, 'rb').read()
    shot = call('POST', '/appScreenshots', json={'data': {
        'type': 'appScreenshots',
        'attributes': {'fileName': os.path.basename(path), 'fileSize': len(data)},
        'relationships': {'appScreenshotSet': {'data': {'type': 'appScreenshotSets', 'id': set_id}}},
    }})['data']
    for op in shot['attributes']['uploadOperations']:
        part = data[op['offset']:op['offset'] + op['length']]
        headers = {h['name']: h['value'] for h in op.get('requestHeaders') or []}
        r = requests.request(op['method'], op['url'], headers=headers, data=part, timeout=120)
        if r.status_code >= 400:
            sys.exit(f'Uploading {path} failed: {r.status_code} {r.text}')
    call('PATCH', f'/appScreenshots/{shot["id"]}', json={'data': {
        'type': 'appScreenshots', 'id': shot['id'],
        'attributes': {'uploaded': True, 'sourceFileChecksum': hashlib.md5(data).hexdigest()},
    }})
    return shot['id']


def wait_until_processed(ids):
    for _ in range(30):
        states = {i: call('GET', f'/appScreenshots/{i}')['data']['attributes']['assetDeliveryState'] for i in ids}
        failed = {i: s for i, s in states.items() if s['state'] == 'FAILED'}
        if failed:
            sys.exit(f'Apple rejected screenshots: {failed}')
        if all(s['state'] == 'COMPLETE' for s in states.values()):
            return
        time.sleep(10)
    print('Apple is still processing the screenshots; check App Store Connect in a few minutes.')


def main():
    app_id, folder = sys.argv[1], sys.argv[2]
    files = sorted(glob.glob(os.path.join(folder, '*.png')))
    if not files:
        sys.exit(f'No .png files in {folder}')
    version = editable_version(app_id)
    print(f"Version {version['attributes']['versionString']} ({version['attributes']['appStoreState']})")
    for loc in call('GET', f"/appStoreVersions/{version['id']}/appStoreVersionLocalizations")['data']:
        set_id = screenshot_set(loc['id'])
        # Replace what is there (including earlier failed uploads), so the order matches the files.
        for old in call('GET', f'/appScreenshotSets/{set_id}/appScreenshots')['data']:
            call('DELETE', f"/appScreenshots/{old['id']}")
        ids = [upload(set_id, f) for f in files]
        wait_until_processed(ids)
        print(f"{loc['attributes']['locale']}: uploaded {len(ids)} screenshots")


if __name__ == '__main__':
    main()
