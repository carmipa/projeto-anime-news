"""
Script de verificação manual dos filtros do AnimeBootNews.
Simula manchetes e verifica se seriam aprovadas ou bloqueadas.
"""
import sys
import os

# Adiciona diretório raiz ao path para importar core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.filters import match_intel

# Configuração simulada (Guild com filtro 'todos' ativo e filtro 'anime')
MOCK_CONFIG_ALL = {"123": {"filters": ["todos"]}}
MOCK_CONFIG_ANIME = {"123": {"filters": ["anime"]}}

TEST_CASES = [
    # (Titulo, Resumo, Deve Passar?, Motivo)
    
    # --- Devem Passar (ANIME) ---
    ("New Demon Slayer Season Announced", "The infinite castle arc begins.", True, "Anime News"),
    ("One Piece Episode 1000 Trailer", "Watch the new PV.", True, "Anime PV"),
    ("Studio MAPPA releases new visual", "Chainsaw man movie visual.", True, "Studio News"),
    
    # --- Devem Falhar (GAMES) ---
    ("Dragon Ball Sparking Zero Gameplay Reveal", "Watch 10 mins of ps5 footage.", False, "Game (gameplay/ps5)"),
    ("Gundam Breaker 4 Release Date", "New nintendo switch game.", False, "Game (switch)"),
    ("Elden Ring Anime announced", "FromSoftware game gets manual adaptation.", True, "Anime adaptation of game is OK? No, if 'game' word is present it might block. Let's test."),
    
    # --- Devem Falhar (MERCH/FASHION) ---
    ("Uniqlo x Naruto T-Shirt Collection", "New apparel available now.", False, "Fashion (t-shirt/apparel)"),
    ("New Bandai Namco Figure", "Detailed statue of Goku.", False, "Merch (figure/statue)"),
    ("Gunpla HG Rising Freedom", "New model kit availability.", False, "Gunpla/Model Kit"),
]

def run_tests():
    print("running Filter Tests...\n")
    passed_count = 0
    
    for title, summary, should_pass, reason in TEST_CASES:
        # Testando com configuração 'todas' para garantir que blacklist funciona mesmo com 'todos'
        result = match_intel("123", title, summary, MOCK_CONFIG_ALL)
        
        status = "PASSED" if result == should_pass else "FAILED"
        if status == "PASSED":
            passed_count += 1
            
        icon = "✅" if status == "PASSED" else "❌"
        res_text = "APPROVED" if result else "BLOCKED"
        
        print(f"{icon} [{status}] '{title}' -> {res_text}")
        print(f"    Expected: {'APPROVED' if should_pass else 'BLOCKED'} ({reason})")
        if status == "FAILED":
             print(f"    ⚠️  CRITICAL FAILURE: Logic is wrong for this case.")
        print("-" * 30)

    print(f"\nTotal: {passed_count}/{len(TEST_CASES)} passed.")

if __name__ == "__main__":
    try:
        run_tests()
    except ImportError:
        # Caso rode fora da raiz e nao ache o modulo
        import sys
        import os
        sys.path.append(os.getcwd())
        run_tests()
