from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from typing import Any

import torch


FALLBACK_COLOURS = (
    "#6F9D69",
    "#C44F55",
    "#8A6AA8",
    "#D18C36",
    "#5E83B4",
    "#4E9895",
    "#A96F5B",
    "#8A7B52",
)


SEMANTIC_COLOURS = {
    "normal": "#6F9D69",
    "good": "#6F9D69",
    "acceptable": "#6F9D69",

    "too_dark": "#D18C36",
    "too dark": "#D18C36",
    "burned": "#D18C36",
    "burnt": "#D18C36",
    "colour": "#D18C36",
    "color": "#D18C36",
    "dark": "#D18C36",

    "too_short": "#8A6AA8",
    "too short": "#8A6AA8",
    "short": "#8A6AA8",

    "fractured": "#C44F55",
    "broken": "#C44F55",
    "cracked": "#C44F55",

    "bent_snack": "#5E83B4",
    "bent snack": "#5E83B4",
    "bent": "#5E83B4",
    "curved": "#5E83B4",
}


CLASS_NAME_KEYS = (
    "class_names",
    "classes",
    "names",
    "labels",
    "label_names",
    "idx_to_class",
    "index_to_class",
    "class_to_idx",
    "class_to_index",
)


CLASS_COLOUR_KEYS = (
    "class_colours",
    "class_colors",
    "colours",
    "colors",
    "label_colours",
    "label_colors",
)


NESTED_METADATA_KEYS = (
    "metadata",
    "meta",
    "config",
    "model_info",
    "classifier",
    "training_config",
    "checkpoint_meta",
)


def _load_checkpoint(
    classifier_path: Path,
) -> Any:

    try:

        return torch.load(
            classifier_path,
            map_location="cpu",
            weights_only=True,
        )

    except TypeError:

        return torch.load(
            classifier_path,
            map_location="cpu",
        )

    except Exception:

        return torch.load(
            classifier_path,
            map_location="cpu",
            weights_only=False,
        )


def _normalise_class_names(
    value: Any,
) -> list[str] | None:

    if isinstance(
        value,
        (list, tuple),
    ):

        names = [
            str(item).strip()
            for item in value
        ]

        return (
            names
            if all(names)
            else None
        )


    if isinstance(
        value,
        dict,
    ):

        if (
            value
            and
            all(
                str(key).isdigit()
                for key
                in value.keys()
            )
        ):

            return [
                str(value[key]).strip()
                for key
                in sorted(
                    value.keys(),
                    key=lambda item:
                        int(item),
                )
            ]


        if (
            value
            and
            all(
                isinstance(index, int)
                for index
                in value.values()
            )
        ):

            return [
                str(name).strip()
                for name, _
                in sorted(
                    value.items(),
                    key=lambda item:
                        item[1],
                )
            ]


    return None


def _find_class_names(
    obj: Any,
    depth: int = 0,
) -> list[str] | None:

    if depth > 6:
        return None


    if isinstance(
        obj,
        dict,
    ):

        for key in CLASS_NAME_KEYS:

            if key not in obj:
                continue

            names = _normalise_class_names(
                obj[key]
            )

            if names:
                return names


        for key in NESTED_METADATA_KEYS:

            if key not in obj:
                continue

            names = _find_class_names(
                obj[key],
                depth + 1,
            )

            if names:
                return names


    for attribute in CLASS_NAME_KEYS:

        try:

            value = getattr(
                obj,
                attribute,
            )

        except Exception:

            continue


        names = _normalise_class_names(
            value
        )

        if names:
            return names


    return None


def _normalise_colour_map(
    value: Any,
    class_names: list[str],
) -> dict[str, str]:

    if isinstance(
        value,
        dict,
    ):

        result = {}

        for key, colour in (
            value.items()
        ):

            if not isinstance(
                colour,
                str,
            ):
                continue


            key_text = str(
                key
            )


            if key_text.isdigit():

                index = int(
                    key_text
                )

                if (
                    0
                    <= index
                    < len(class_names)
                ):

                    result[
                        class_names[index]
                    ] = colour

            else:

                result[
                    key_text
                ] = colour


        return result


    if isinstance(
        value,
        (list, tuple),
    ):

        return {
            class_names[index]:
                str(colour)

            for index, colour
            in enumerate(value)

            if (
                index
                < len(class_names)
            )
        }


    return {}


def _find_colour_map(
    obj: Any,
    class_names: list[str],
    depth: int = 0,
) -> dict[str, str]:

    if depth > 6:
        return {}


    if isinstance(
        obj,
        dict,
    ):

        for key in CLASS_COLOUR_KEYS:

            if key not in obj:
                continue

            result = _normalise_colour_map(
                obj[key],
                class_names,
            )

            if result:
                return result


        for key in NESTED_METADATA_KEYS:

            if key not in obj:
                continue

            result = _find_colour_map(
                obj[key],
                class_names,
                depth + 1,
            )

            if result:
                return result


    return {}


def _normalise_name(
    value: str,
) -> str:

    return (
        value
        .strip()
        .lower()
    )


def _display_name(
    class_name: str,
) -> str:

    return (
        class_name
        .replace("_", " ")
        .replace("-", " ")
        .strip()
        .title()
    )


def _slug(
    value: str,
) -> str:

    return (
        re.sub(
            r"[^a-z0-9]+",
            "-",
            value.lower(),
        )
        .strip("-")
    )


def _is_normal_class(
    class_name: str,
) -> bool:

    value = _normalise_name(
        class_name
    )

    return any(
        keyword in value
        for keyword
        in (
            "normal",
            "good",
            "acceptable",
        )
    )


def _fallback_colour_for_class(
    class_name: str,
    index: int,
) -> str:

    value = _normalise_name(
        class_name
    )


    if value in SEMANTIC_COLOURS:

        return (
            SEMANTIC_COLOURS[
                value
            ]
        )


    for keyword, colour in (
        SEMANTIC_COLOURS.items()
    ):

        if keyword in value:
            return colour


    return (
        FALLBACK_COLOURS[
            index
            %
            len(
                FALLBACK_COLOURS
            )
        ]
    )


def _checkpoint_colour_for_class(
    checkpoint_colour_map: dict[str, str],
    class_name: str,
) -> str | None:

    if class_name in (
        checkpoint_colour_map
    ):

        return (
            checkpoint_colour_map[
                class_name
            ]
        )


    lower_lookup = {
        str(key)
        .strip()
        .lower():
            colour

        for key, colour
        in checkpoint_colour_map.items()
    }


    return (
        lower_lookup.get(
            class_name
            .strip()
            .lower()
        )
    )


@lru_cache(
    maxsize=8
)
def get_classifier_ui_metadata(
    classifier_path_string: str,
) -> dict:

    classifier_path = Path(
        classifier_path_string
    )


    if not classifier_path.exists():

        raise FileNotFoundError(
            "Classifier checkpoint not found: "
            f"{classifier_path}"
        )


    checkpoint = _load_checkpoint(
        classifier_path
    )


    class_names = _find_class_names(
        checkpoint
    )


    if not class_names:

        raise RuntimeError(
            "The classifier checkpoint was loaded, "
            "but no class-name metadata was found."
        )


    checkpoint_colour_map = (
        _find_colour_map(
            checkpoint,
            class_names,
        )
    )


    classes = []


    for index, class_name in enumerate(
        class_names
    ):

        checkpoint_colour = (
            _checkpoint_colour_for_class(
                checkpoint_colour_map,
                class_name,
            )
        )


        colour = (
            checkpoint_colour
            or
            _fallback_colour_for_class(
                class_name,
                index,
            )
        )


        is_normal = _is_normal_class(
            class_name
        )


        classes.append(
            {
                "index":
                    index,

                "name":
                    class_name,

                "display_name":
                    _display_name(
                        class_name
                    ),

                "slug":
                    _slug(
                        class_name
                    ),

                "colour":
                    colour,

                "decision":
                    (
                        "NORMAL"
                        if is_normal
                        else
                        "DEFECT"
                    ),

                "is_normal":
                    is_normal,
            }
        )


    return {
        "classifier_file":
            classifier_path.name,

        "classifier_path":
            str(
                classifier_path
            ),

        "class_count":
            len(
                classes
            ),

        "classes":
            classes,
    }
