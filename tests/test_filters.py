"""
Smoke tests básicos para verificar que o projeto está configurado corretamente.
Não testa lógica complexa para evitar dependências do Discord token.
"""
import os
import json


def test_config_files_exist():
    """Verifica que arquivos de configuração existem."""
    assert os.path.exists("sources.json"), "sources.json deve existir"
    assert os.path.exists("settings.py"), "settings.py deve existir"
    assert os.path.exists("main.py"), "main.py deve existir"


def _iter_source_urls(data=None):
    """
    URLs das fontes, lidas pelo MESMO carregador que a varredura usa.

    Antes esta função reimplementava o achatamento do sources.json. Quando o
    ficheiro ganhou metadados por fonte, a cópia passou a devolver dicionários
    em vez de strings e os testes abaixo deixaram de verificar o que diziam
    verificar — sem falhar. Sonda reimplementada mente; usar o código real.
    """
    from core.sources import load_sources
    return load_sources()


def test_sources_json_structure():
    """Verifica estrutura de sources.json: dict de categorias com listas de fontes."""
    with open("sources.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict), "sources.json deve ser um objeto"

    # Deve ter pelo menos uma categoria (ex: youtube_feeds, official_sites)
    assert data, "sources.json não pode estar vazio"

    # Cada categoria deve ser dict (subcategorias) ou list (fontes diretas)
    for name, category in data.items():
        assert isinstance(category, (dict, list)), f"Categoria '{name}' deve ser dict ou list"

    # Deve resultar em pelo menos uma URL utilizável PELO CARREGADOR REAL
    assert _iter_source_urls(), "sources.json deve conter pelo menos uma URL"


def test_no_invalid_youtube_urls():
    """Verifica que não há URLs do YouTube com @ (formato inválido: handle, não feed Atom)."""
    urls = _iter_source_urls()
    assert urls, "nenhuma URL carregada — o teste abaixo não provaria nada"

    for url in urls:
        assert isinstance(url, str), f"load_sources devolveu {type(url).__name__}, não URL"
        if "youtube.com" in url or "youtu.be" in url:
            assert "@" not in url, f"YouTube URL inválida (use channel_id): {url}"


def test_requirements_has_dependencies():
    """Verifica que requirements.txt tem dependências essenciais."""
    # Tenta diferentes encodings (requirements.txt pode ser UTF-16 no Windows)
    for encoding in ["utf-8", "utf-16", "latin-1"]:
        try:
            with open("requirements.txt", "r", encoding=encoding) as f:
                content = f.read().lower()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    assert "discord" in content, "requirements.txt deve incluir discord.py"
    assert "feedparser" in content, "requirements.txt deve incluir feedparser"
    assert "aiohttp" in content, "requirements.txt deve incluir aiohttp"


def test_scanner_has_ssl_fix():
    """Verifica que o scanner usa certifi para SSL (o contexto SSL vive em core/scanner.py)."""
    with open(os.path.join("core", "scanner.py"), "r", encoding="utf-8") as f:
        content = f.read()

    # Deve usar certifi
    assert "certifi" in content, "core/scanner.py deve usar certifi para SSL seguro"

    # NÃO deve ter CERT_NONE (inseguro)
    assert "CERT_NONE" not in content, "core/scanner.py não deve usar CERT_NONE (inseguro)"

