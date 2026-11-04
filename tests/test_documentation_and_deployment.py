from pathlib import Path
import tomllib
import yaml
from scripts.service_catalog import SERVICES

ROOT=Path(__file__).resolve().parents[1]

def test_all_services_have_independent_packages_images_and_tests():
    for slug,_,port in SERVICES:
        root=ROOT/'services'/('svc-'+slug)
        project=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))
        assert project['project']['name']=='svc-'+slug
        assert (root/'Dockerfile').is_file()
        assert list((root/'tests').rglob('test_*.py'))
        assert (root/'src'/('svc_'+slug.replace('-','_'))/'app.py').is_file()

def test_topology_has_private_service_volumes_and_database_credentials():
    compose=yaml.safe_load((ROOT/'docker-compose.yml').read_text(encoding='utf-8'))
    assert len(compose['services'])==17
    credentials=set()
    for slug,_,port in SERVICES:
        service=compose['services']['svc-'+slug]
        assert 'ports' not in service
        assert f'{slug}-data:/data' in service['volumes']
        assert str(port) in service['expose']
        if url:=service['environment'].get('DATABASE_URL'):
            assert url not in credentials
            credentials.add(url)
    assert len(credentials)==10

def test_source_map_references_existing_sources_and_destinations():
    import ast
    import json
    rows=json.loads((ROOT/'docs/migration/source-map.json').read_text(encoding='utf-8'))
    for row in rows:
        assert (ROOT/row['source']).is_file()
        assert (ROOT/row['destination']).is_file()
        assert Path(row['source']).suffix not in {'.pdf','.txt','.db','.pfx','.p12'}
        if Path(row['source']).name.startswith('test_') and Path(row['source']).suffix=='.py':
            def test_count(path):
                return sum(isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_')
                    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))))
            assert test_count(ROOT/row['destination']) >= test_count(ROOT/row['source'])
