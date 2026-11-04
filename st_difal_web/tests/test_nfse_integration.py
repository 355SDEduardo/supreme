from io import BytesIO
import json
import subprocess
import sys
from threading import Thread
from urllib.request import urlopen
from werkzeug.serving import make_server

import pytest

from app import create_app
from cli import build_parser, run_cli
from core.nfse_pipeline import process_nfse_batch
from tests.nfse_samples import KEY, abrasf, event, national, paulistana, zipped
from tests.sample_data import SAMPLE_XML


def test_mixed_batch_response_duplicates_and_quarantine():
    response = b'<ConsultarNfseResposta>' + abrasf(number='001') + abrasf(number='002') + b'</ConsultarNfseResposta>'
    state = process_nfse_batch([('lote.zip', zipped([('a.xml', national()), ('sp.xml', paulistana()),
        ('response.xml', response), ('bad.xml', b'<x>'), ('same.xml', national())]))])
    assert len(state.documents) == 4
    assert state.total_processed == 5
    assert len(state.issues) == 1
    assert any('duplicado' in message for message in state.logs)


def test_batch_global_resource_limits():
    with pytest.raises(ValueError, match='Lote NFS-e'):
        process_nfse_batch([('a.xml', national()), ('b.xml', national())], max_xml_files=1)
    with pytest.raises(ValueError, match='Lote NFS-e'):
        process_nfse_batch([('a.xml', national())], max_total_bytes=20)


@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING': True, 'SECRET_KEY': 'synthetic', 'FISCAL_DATA_PATH': tmp_path / 'fiscal.json'})


def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return session['csrf_token']


def upload(client, content=None, **kwargs):
    return client.post('/nfse/processar', data={'csrf_token': csrf(client),
        'arquivos_nfse': (BytesIO(content or national()), 'nota.xml')}, **kwargs)


def test_web_upload_exports_csrf_clear_and_session_privacy(app):
    client = app.test_client()
    assert client.get('/nfse/exportar/json').status_code == 404
    assert client.post('/nfse/processar').status_code == 400
    response = upload(client, follow_redirects=True)
    assert response.status_code == 200
    assert 'auditoria-nfse' in response.text and 'Prestadora sintética' in response.text
    for path in ('excel', 'csv/notas', 'csv/apontamentos', 'json'):
        exported = client.get('/nfse/exportar/' + path)
        assert exported.status_code == 200
        assert 'attachment' in exported.headers['Content-Disposition']
        assert exported.headers['Cache-Control'] == 'no-store'
    assert client.get('/nfse/exportar/csv/unknown').status_code == 404
    assert app.test_client().get('/nfse/exportar/json').status_code == 404
    assert client.post('/nfse/limpar', data={'csrf_token': csrf(client)}).status_code == 302
    assert client.get('/nfse/exportar/json').status_code == 404


def test_web_ajax_xss_mixed_zip_and_failure_preserves_previous(app):
    client = app.test_client()
    dangerous = national().replace('Prestadora sintética'.encode(), b'&lt;script&gt;alert(1)&lt;/script&gt;')
    response = upload(client, dangerous, headers={'Accept': 'application/json'})
    assert response.status_code == 200
    assert response.json['documents'][0]['provider']['name'] == '<script>alert(1)</script>'
    assert '<script>alert(1)</script>' not in client.get('/').text
    previous = client.get('/nfse/exportar/json').json
    upload(client, b'<invalid>')
    assert client.get('/nfse/exportar/json').json == previous
    response = client.post('/nfse/processar', data={'csrf_token': csrf(client),
        'arquivos_nfse': (BytesIO(zipped([('a.xml', national()), ('event.xml', event()), ('bad.xml', b'<x>')])), 'lote.zip')},
        headers={'Accept': 'application/json'})
    assert response.json['documents'][0]['status'] == 'CANCELLED'
    assert response.json['issues']


def test_nfse_and_nfe_results_survive_processing_and_independent_clear(app):
    client = app.test_client()
    upload(client)
    response = client.post('/processar', data={'csrf_token': csrf(client),
        'xml_files': (BytesIO(SAMPLE_XML), 'nfe.xml')})
    assert response.status_code == 302
    assert client.get('/nfse/exportar/json').status_code == 200
    assert client.get('/download/relatorio.json').status_code == 200
    upload(client)
    assert client.get('/download/relatorio.json').status_code == 200
    client.post('/nfse/limpar', data={'csrf_token': csrf(client)})
    assert client.get('/download/relatorio.json').status_code == 200
    upload(client)
    client.post('/limpar-sessao', data={'csrf_token': csrf(client)})
    assert client.get('/nfse/exportar/json').status_code == 404


def test_cli_all_exports_short_o_and_full_findings(tmp_path, capsys):
    path = tmp_path / 'nota.XML'
    path.write_bytes(national())
    output = tmp_path / 'out'
    args = build_parser().parse_args(['--nfse', '-i', str(tmp_path), '-o', str(output / 'r.xlsx'),
        '--output-json', str(output / 'r.json'), '--output-csv', str(output / 'r'), '--min-severity', 'CRITICAL'])
    assert run_cli(args) == 0
    assert (output / 'r.xlsx').exists()
    assert (output / 'r_notas.csv').read_bytes().startswith(b'\xef\xbb\xbf')
    assert (output / 'r_apontamentos.csv').exists()
    assert json.loads((output / 'r.json').read_text(encoding='utf-8'))['documents']
    assert 'NFS-e:' in capsys.readouterr().out
    # Existing -o continues to select NF-e operations.
    assert build_parser().parse_args(['-o', 'estadual']).operacao == 'estadual'


def test_cli_exit_codes_missing_bad_partial_critical_and_collisions(tmp_path):
    parser = build_parser()
    assert run_cli(parser.parse_args(['--nfse'])) == 1
    assert run_cli(parser.parse_args(['--nfse', '-i', str(tmp_path / 'missing')])) == 1
    broken = tmp_path / 'bad.zip'
    broken.write_bytes(b'invalid')
    assert run_cli(parser.parse_args(['--nfse', '-i', str(broken)])) == 1
    path = tmp_path / 'nota.xml'
    path.write_bytes(national(rate='6.00'))
    assert run_cli(parser.parse_args(['--nfse', '-i', str(path), '-q'])) == 2
    assert run_cli(parser.parse_args(['--nfse', '-i', str(path), '--output-json', str(path)])) == 1
    assert path.read_bytes() == national(rate='6.00')
    collision = tmp_path / 'r.json'
    assert run_cli(parser.parse_args(['--nfse', '-i', str(path), '--output-json', str(collision), '--output-excel', str(collision)])) == 1


def test_cli_subprocess_critical_exit_and_no_interactive_prompt(tmp_path):
    path = tmp_path / 'nota.xml'
    path.write_bytes(national(rate='6.00'))
    result = subprocess.run([sys.executable, 'cli.py', '--nfse', '-i', str(path), '-q'],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 2, result.stderr
    assert 'NFS-e:' in result.stdout


def test_actual_http_server_and_static_assets(app):
    server = make_server('127.0.0.1', 0, app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f'http://127.0.0.1:{server.server_port}'
        with urlopen(base + '/?tab=auditoria-nfse', timeout=5) as response:
            assert response.status == 200
            assert 'data-tab-target="auditoria-nfse">NFS-e</button>' in response.read().decode('utf-8')
            assert response.headers['Content-Security-Policy']
        for asset in ('app.js', 'styles.css'):
            with urlopen(base + '/static/' + asset, timeout=5) as response:
                assert response.status == 200
                assert response.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
