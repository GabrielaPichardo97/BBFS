"""Small, explicit acquisition profiles for the first Bronze batches."""

from __future__ import annotations

from baby_first_steps_medallion.bronze.models import QueryProfile

QUERY_PROFILES: dict[str, QueryProfile] = {
    "motor_sensory": QueryProfile(
        profile_id="motor_sensory",
        terms=(
            "estimulación sensorial bebés",
            "desarrollo motor lactantes",
            "sensory play infant development",
            "fine motor activities infants toddlers",
        ),
    ),
    "language_interaction": QueryProfile(
        profile_id="language_interaction",
        terms=(
            "estimulación del lenguaje bebés",
            "lectura compartida desarrollo infantil",
            "shared reading infant language development",
            "caregiver child interaction language",
        ),
    ),
    "music_play_materials": QueryProfile(
        profile_id="music_play_materials",
        terms=(
            "música movimiento primera infancia",
            "materiales de juego desarrollo infantil",
            "music movement early childhood development",
            "play materials infant development",
        ),
    ),
}


def select_profiles(value: str | None) -> list[QueryProfile]:
    """Resolve a comma-separated CLI selection without accepting unknown profiles."""
    names = list(QUERY_PROFILES) if value is None else [item.strip() for item in value.split(",")]
    names = [name for name in names if name]
    unknown = sorted(set(names) - set(QUERY_PROFILES))
    if unknown:
        raise ValueError(f"Perfiles no reconocidos: {', '.join(unknown)}")
    if not names:
        raise ValueError("Debe seleccionarse al menos un perfil de consulta.")
    return [QUERY_PROFILES[name] for name in names]
