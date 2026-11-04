import os
from svc_pdf_tools.housekeeping import cleanup_expired_outputs

def test_only_expired_server_outputs_are_removed(tmp_path):
    expired=tmp_path/('a'*32+'.pdf')
    recent=tmp_path/('b'*32+'.zip')
    original=tmp_path/'original.pdf'
    for path in (expired,recent,original):
        path.write_bytes(b'test')
    os.utime(expired,(1,1))
    os.utime(original,(1,1))
    assert cleanup_expired_outputs(tmp_path,ttl=7200)==1
    assert not expired.exists()
    assert recent.exists() and original.exists()
