"""
Guardas do roteamento de arquivos de ESTADO para DATA_DIR.

O bug que isto resolve: bind mount de arquivo único no Docker torna o rename
atômico (os.replace) impossível (EBUSY), e o bot caía no fallback não-atômico,
avisando a cada escrita. Com os arquivos de estado num DIRETÓRIO (DATA_DIR), o
os.replace volta a funcionar. Estas guardas provam o roteamento e que estáticos
(sources.json, translations/) NÃO são desviados.
"""
import os

import utils.storage as st


def test_estado_vai_para_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(st, "DATA_DIR", str(tmp_path))
    for nome in ("config.json", "history.json", "state.json", "audit.jsonl", "audit.json"):
        assert st.p(nome) == os.path.abspath(os.path.join(str(tmp_path), nome)), nome


def test_estaticos_nao_vao_para_data_dir(monkeypatch, tmp_path):
    # sources.json (catálogo) e caminhos com separador continuam relativos ao app.
    monkeypatch.setattr(st, "DATA_DIR", str(tmp_path))
    assert st.p("sources.json") == os.path.abspath("sources.json")
    assert st.p("translations/en_US.json") == os.path.abspath("translations/en_US.json")
    assert st.p("web/templates") == os.path.abspath("web/templates")


def test_sem_data_dir_comportamento_antigo(monkeypatch):
    # DATA_DIR vazio ⇒ idêntico ao anterior (cwd) — não mexe no uso local.
    monkeypatch.setattr(st, "DATA_DIR", "")
    assert st.p("config.json") == os.path.abspath("config.json")


def test_save_atomico_em_diretorio(monkeypatch, tmp_path, caplog):
    # Com DATA_DIR = diretório real, o os.replace funciona e NÃO cai no fallback:
    # o aviso "escrita atômica indisponível" não aparece e não sobra .tmp.
    monkeypatch.setattr(st, "DATA_DIR", str(tmp_path))
    alvo = st.p("state.json")
    with caplog.at_level("WARNING", logger="AnimeBotIntel"):
        st.save_json_safe(alvo, {"_meta": {"ok": True}})
    assert st.load_json_safe(alvo, None) == {"_meta": {"ok": True}}
    assert not os.path.exists(alvo + ".tmp")
    assert "atômica indisponível" not in caplog.text
