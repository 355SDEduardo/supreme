"""
Script de Inicialização da Aplicação NFS-e Nacional Intelligence Suite.
Executa o servidor local FastAPI com reload automático e abre na porta 8000.
"""

import sys
import uvicorn
from pathlib import Path

# Adiciona o diretório atual ao sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    print("=" * 70)
    print("  NFS-e Nacional Intelligence Suite")
    print("  Parser Sped v1.01 | Armazenamento JSON | Dashboard | Planilhas Excel")
    print("=" * 70)
    print("  Servidor iniciado em: http://127.0.0.1:8000")
    print("  Documentação Swagger: http://127.0.0.1:8000/docs")
    print("=" * 70)

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
