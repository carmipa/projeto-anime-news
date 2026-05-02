"""
Configuration validation and schema checking.
"""
import json
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

from utils.storage import p, load_json_safe
from utils.exceptions import ConfigurationError
from utils.logger import log


class ConfigValidator:
    """Validador de configuração."""
    
    # Schema para config.json
    CONFIG_SCHEMA = {
        "type": "object",
        "patternProperties": {
            "^[0-9]+$": {  # Guild ID como chave
                "type": "object",
                "properties": {
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["anime", "news", "music", "games", "filmes", "todos"]
                        }
                    },
                    "channel_id": {"type": "integer"},
                    "language": {
                        "type": "string",
                        "enum": ["pt_BR", "en_US", "es_ES", "it_IT"]
                    },
                    "enabled": {"type": "boolean"}
                },
                "required": ["channel_id", "filters"]
            }
        }
    }
    
    # Schema para sources.json
    SOURCES_SCHEMA = {
        "type": "object",
        "properties": {
            "youtube_feeds": {"type": "object"},
            "official_sites": {"type": "object"},
            "rss_feeds": {"type": "object"}
        }
    }
    
    @staticmethod
    def validate_config(config_path: str = "config.json") -> Dict[str, Any]:
        """
        Valida config.json.
        
        Args:
            config_path: Caminho do arquivo
        
        Returns:
            Config validado
        
        Raises:
            ConfigurationError: Se configuração inválida
        """
        config = load_json_safe(p(config_path), {})
        
        if not isinstance(config, dict):
            raise ConfigurationError(f"{config_path} deve ser um objeto JSON")
        
        validated = {}
        errors = []
        
        for guild_id_str, guild_config in config.items():
            # Valida guild ID
            if not guild_id_str.isdigit():
                errors.append(f"Guild ID inválido: {guild_id_str}")
                continue
            
            # Valida estrutura
            if not isinstance(guild_config, dict):
                errors.append(f"Config da guild {guild_id_str} deve ser um objeto")
                continue
            
            # Valida campos obrigatórios
            if "channel_id" not in guild_config:
                errors.append(f"Guild {guild_id_str} sem channel_id")
                continue
            
            if "filters" not in guild_config:
                errors.append(f"Guild {guild_id_str} sem filters")
                continue
            
            # Valida channel_id
            try:
                channel_id = int(guild_config["channel_id"])
                if channel_id < 100000000000000000:
                    errors.append(f"Guild {guild_id_str}: channel_id inválido")
                    continue
            except (ValueError, TypeError):
                errors.append(f"Guild {guild_id_str}: channel_id deve ser numérico")
                continue
            
            # Valida filters
            filters = guild_config.get("filters", [])
            if not isinstance(filters, list):
                errors.append(f"Guild {guild_id_str}: filters deve ser uma lista")
                continue
            
            valid_filters = {"anime", "news", "music", "games", "filmes", "todos"}
            invalid_filters = [f for f in filters if f not in valid_filters]
            if invalid_filters:
                errors.append(f"Guild {guild_id_str}: filtros inválidos: {invalid_filters}")
                continue
            
            # Valida language
            language = guild_config.get("language", "pt_BR")
            valid_languages = {"pt_BR", "en_US", "es_ES", "it_IT"}
            if language not in valid_languages:
                errors.append(f"Guild {guild_id_str}: idioma inválido: {language}")
                language = "pt_BR"  # Fallback
            
            # Configuração validada
            validated[guild_id_str] = {
                "channel_id": channel_id,
                "filters": filters,
                "language": language,
                "enabled": guild_config.get("enabled", True)
            }
        
        if errors:
            error_msg = "Erros de validação:\n" + "\n".join(f"  - {e}" for e in errors)
            log.warning(error_msg)
            # Não falha completamente, apenas loga warnings
        
        return validated
    
    @staticmethod
    def validate_sources(sources_path: str = "sources.json") -> Dict[str, Any]:
        """
        Valida sources.json.
        
        Args:
            sources_path: Caminho do arquivo
        
        Returns:
            Sources validado
        
        Raises:
            ConfigurationError: Se configuração inválida
        """
        sources = load_json_safe(p(sources_path), {})
        
        if not isinstance(sources, dict):
            raise ConfigurationError(f"{sources_path} deve ser um objeto JSON")
        
        validated = {
            "youtube_feeds": {},
            "official_sites": {},
            "rss_feeds": {}
        }
        
        # Valida estrutura básica
        for category in ["youtube_feeds", "official_sites", "rss_feeds"]:
            if category in sources:
                cat_data = sources[category]
                if isinstance(cat_data, dict):
                    validated[category] = cat_data
                elif isinstance(cat_data, list):
                    validated[category] = {"default": cat_data}
        
        return validated
    
    @staticmethod
    def validate_all() -> Dict[str, Any]:
        """
        Valida todos os arquivos de configuração.
        
        Returns:
            Dict com resultados da validação
        """
        results = {
            "config": None,
            "sources": None,
            "errors": []
        }
        
        try:
            results["config"] = ConfigValidator.validate_config()
        except Exception as e:
            results["errors"].append(f"Erro ao validar config.json: {e}")
        
        try:
            results["sources"] = ConfigValidator.validate_sources()
        except Exception as e:
            results["errors"].append(f"Erro ao validar sources.json: {e}")
        
        return results
