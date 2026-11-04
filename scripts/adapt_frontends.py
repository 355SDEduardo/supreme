"""One-time adaptation of extracted assets to gateway routes and CSP."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / 'frontend/modules'

def main():
    for module, route in [('nfse-intelligence','nfse'),('tax-audit','tax-audit'),('pdf-tools','pdf'),('portal-contabil','portal')]:
        folder = ROOT / module
        for path in folder.rglob('*'):
            if not path.is_file() or path.suffix not in {'.html','.js','.css'} or path.name == 'inline-handlers.js':
                continue
            text = path.read_text(encoding='utf-8')
            text = text.replace('/static/', f'/app/modules/{module}/')
            if route in {'nfse','tax-audit'}:
                text = re.sub(r'/api/(?!v1/)', '/api/v1/' + route + '/', text)
            if route == 'pdf':
                text = re.sub(r'(?<!/v1)/pdf/', '/api/v1/pdf/', text).replace('/api/status','/api/v1/pdf/status')
            if path.suffix == '.html' and '/assets/module-context.js' not in text:
                handlers = []
                def handler(match):
                    index = len(handlers)
                    event, quote, code = match.group(1), match.group(2), match.group(3)
                    import html
                    handlers.append(f'document.querySelectorAll("[data-handler-{index}]").forEach(el=>el.addEventListener("{event}",function(event){{{html.unescape(code)}}}));')
                    return f'data-handler-{index}=""'
                text = re.sub(r'\bon(\w+)\s*=\s*([\"\'])(.*?)\2', handler, text, flags=re.S)
                chunks = []
                def inline(match):
                    if 'src=' in match.group(1):
                        return match.group(0)
                    index = len(chunks)
                    chunks.append(match.group(2))
                    return f'<script src="./inline-{index}.js" defer></script>'
                text = re.sub(r'<script([^>]*)>(.*?)</script>', inline, text, flags=re.S)
                text = text.replace('<head>', '<head><script src="/assets/module-context.js"></script>', 1)
                text = text.replace('</body>', '<script src="./inline-handlers.js" defer></script></body>')
                for index, code in enumerate(chunks):
                    (folder / f'inline-{index}.js').write_text(code,encoding='utf-8')
                (folder/'inline-handlers.js').write_text('\n'.join(handlers), encoding='utf-8')
            path.write_text(text,encoding='utf-8')

if __name__ == '__main__':
    main()
