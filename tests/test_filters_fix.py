#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de teste rápido para verificar se os filtros estão bloqueando corretamente
os conteúdos reportados pelo usuário.
"""
import sys
import os
import io

# Configurar encoding UTF-8 para Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.append(os.path.dirname(__file__))

from core.filters import match_intel

# Configuração de teste
CONFIG = {
    "417746665219424277": {
        "filters": ["anime", "news", "games", "filmes"],
        "channel_id": 1426541539978510490,
        "language": "pt_BR"
    }
}

GUILD_ID = "417746665219424277"

# Casos reportados pelo usuário que DEVEM ser bloqueados
TEST_CASES = [
    {
        "title": "\"Se eu pudesse passar uma coisa\" | Clássico Mundial de Beisebol 2026 | Netflix Japão",
        "summary": "Netflix Japan",
        "source": "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q",
        "expected": False,
        "reason": "Beisebol + Netflix Japan"
    },
    {
        "title": "#3 Samurai Japan Manager Pressão para se tornar o melhor do mundo: Tatsunori Hara x Kazunari Ninomiya | Clássico Mundial de Beisebol de 2026",
        "summary": "Netflix Japan",
        "source": "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q",
        "expected": False,
        "reason": "Beisebol + Manager + Netflix Japan"
    },
    {
        "title": "Bem-vindo ao Lanche \"Ai\" | Este sou eu | Netflix Japão",
        "summary": "Netflix Japan",
        "source": "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q",
        "expected": False,
        "reason": "Netflix Japan + Este sou eu"
    },
    {
        "title": "Caso com as circunstâncias de Takuya e Ai | Este sou eu | Netflix Japão",
        "summary": "Netflix Japan",
        "source": "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q",
        "expected": False,
        "reason": "Netflix Japan + circunstâncias"
    },
    {
        "title": "\"Clássico Mundial de Beisebol 2026\" | Canção de torcida do torneio Netflix | Koshi Inaba \"Toque\" | Filme Especial",
        "summary": "Netflix Japan",
        "source": "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q",
        "expected": False,
        "reason": "Beisebol + Canção de torcida + Netflix"
    },
    {
        "title": "Haruki Mochizuki se torna Ai! GRWM & Set Tour｜This is I｜Netflix Japan",
        "summary": "Netflix Japan",
        "source": "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q",
        "expected": False,
        "reason": "GRWM + Set Tour + Netflix Japan"
    },
    {
        "title": "Kim Seon-ho x Go Yoon-jung - Primeiro beijo em frente a uma cachoeira particular | Você consegue interpretar o amor? | Netflix Japão",
        "summary": "Netflix Japan",
        "source": "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q",
        "expected": False,
        "reason": "Netflix Japan + série live-action"
    },
    {
        "title": "Tour \"Green Room\" de Boys | O namorado 2 | Netflix Japão",
        "summary": "Netflix Japan",
        "source": "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q",
        "expected": False,
        "reason": "Green Room + O namorado + Netflix Japan"
    },
    # Casos que DEVEM passar (anime relacionado)
    {
        "title": "New Gundam Anime Trailer Released",
        "summary": "Sunrise studio announces new series",
        "source": "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q",
        "expected": True,
        "reason": "Gundam é anime relacionado"
    },
    {
        "title": "Crunchyroll adds new Manga titles",
        "summary": "Spring season announcements",
        "source": "https://rss.feed/test",
        "expected": True,
        "reason": "Crunchyroll + Manga são relacionados a anime"
    },
]

def main():
    print("=" * 80)
    print("TESTE DE FILTROS - Verificação de Correções")
    print("=" * 80)
    print()
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(TEST_CASES, 1):
        result = match_intel(
            GUILD_ID,
            case["title"],
            case["summary"],
            CONFIG,
            source=case["source"]
        )
        
        status = "[OK] PASSOU" if result == case["expected"] else "[X] FALHOU"
        if result == case["expected"]:
            passed += 1
        else:
            failed += 1
        
        print(f"Teste {i}: {status}")
        print(f"  Título: {case['title'][:70]}...")
        print(f"  Fonte: {case['source'][:60]}...")
        print(f"  Esperado: {'BLOQUEAR' if not case['expected'] else 'PERMITIR'}")
        print(f"  Resultado: {'BLOQUEADO' if not result else 'PERMITIDO'}")
        print(f"  Motivo: {case['reason']}")
        print()
    
    print("=" * 80)
    print(f"RESULTADO FINAL: {passed} passaram, {failed} falharam")
    print("=" * 80)
    
    if failed > 0:
        print("\n[AVISO] ALGUNS TESTES FALHARAM! Verifique os filtros.")
        sys.exit(1)
    else:
        print("\n[OK] TODOS OS TESTES PASSARAM!")
        sys.exit(0)

if __name__ == "__main__":
    main()
