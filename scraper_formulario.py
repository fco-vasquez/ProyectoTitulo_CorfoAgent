import json
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def _get_label_for_control(ctrl) -> str:
    """Return a human readable label for the control if possible."""
    find = ctrl.find_element
    try:
        label = find(
            By.XPATH,
            "./ancestor::div[contains(@class,'form-group')][1]//label",
        )
        text = label.text.strip()
        if text:
            return text
    except Exception:
        pass

    try:
        parent_label = find(By.XPATH, "./parent::label")
        text = parent_label.text.strip()
        if text:
            return text
    except Exception:
        pass

    try:
        control_id = ctrl.get_attribute("id")
        if control_id:
            label = ctrl.find_element(By.XPATH, f"//label[@for='{control_id}']")
            text = label.text.strip()
            if text:
                return text
    except Exception:
        pass

    placeholder = (
        ctrl.get_attribute("placeholder")
        or ctrl.get_attribute("name")
        or ctrl.get_attribute("id")
        or ""
    )
    return placeholder.strip()


def _control_type(ctrl) -> str:
    """Return the semantic type of the control."""
    tag = (ctrl.tag_name or "").lower()
    if tag == "textarea":
        return "textarea"
    if tag == "select":
        return "select"
    if tag == "input":
        return (ctrl.get_attribute("type") or "text").lower()
    return tag


def _is_required(ctrl) -> bool:
    required_attr = ctrl.get_attribute("required")
    aria_required = ctrl.get_attribute("aria-required")
    classes = (ctrl.get_attribute("class") or "").lower()
    return bool(required_attr or aria_required or "required" in classes)


def _should_skip_control(ctrl_type: str) -> bool:
    return ctrl_type in {"hidden", "button", "submit", "reset"}


def extract_form_to_json(
    driver,
    output_path: str = "formulario.json",
    wait_seconds: int = 30,
    panel_selector: str = "div.panel-body",
    initial_wait_seconds: int = 20,
) -> List[Dict[str, Any]]:
    """
    Wait until at least one panel defined by `panel_selector` is present, then
    collect the visible controls inside each panel body.

    Each field in the resulting list contains the control label (nombre), control
    type (tipo) and whether the field is marked as required (obligatorio). Some
    optional metadata is included to aid later automation (id, name, options).
    """

    # Give the site extra time to cargar assets dinámicos antes de buscar el panel.
    if initial_wait_seconds > 0:
        time.sleep(initial_wait_seconds)

    wait = WebDriverWait(driver, wait_seconds)
    try:
        panels = wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, panel_selector))
        )
    except TimeoutException as exc:
        raise RuntimeError(
            f"No se encontro ningun contenedor '{panel_selector}' antes del timeout."
        ) from exc

    # Allow dynamic content to settle (ajax loaders, etc.)
    time.sleep(1)

    fields: List[Dict[str, Any]] = []
    grouped_radios: Set[Tuple[int, str]] = set()

    for panel_index, panel in enumerate(panels):
        try:
            if not panel.is_displayed():
                continue
        except Exception:
            continue

        controls = panel.find_elements(By.CSS_SELECTOR, "input, textarea, select")
        for ctrl in controls:
            try:
                if not ctrl.is_displayed():
                    continue
            except Exception:
                continue

            ctrl_type = _control_type(ctrl)
            if _should_skip_control(ctrl_type):
                continue

            if ctrl_type == "radio":
                radio_key = (
                    panel_index,
                    ctrl.get_attribute("name") or ctrl.get_attribute("id") or "",
                )
                if radio_key in grouped_radios:
                    continue
                grouped_radios.add(radio_key)

            label = _get_label_for_control(ctrl) or None
            field: Dict[str, Any] = {
                "nombre": label,
                "tipo": ctrl_type,
                "obligatorio": _is_required(ctrl),
            }

            control_id: Optional[str] = ctrl.get_attribute("id")
            control_name: Optional[str] = ctrl.get_attribute("name")
            if control_id:
                field["id"] = control_id
            if control_name:
                field["name"] = control_name

            if ctrl_type == "select":
                options: List[Dict[str, Optional[str]]] = []
                for option in ctrl.find_elements(By.TAG_NAME, "option"):
                    options.append(
                        {
                            "value": option.get_attribute("value"),
                            "text": option.text,
                        }
                    )
                field["options"] = options
            elif ctrl_type in {"text", "textarea", "number", "file", "email", "tel"}:
                field["placeholder"] = ctrl.get_attribute("placeholder") or None
                field["maxlength"] = ctrl.get_attribute("maxlength") or None
            elif ctrl_type in {"radio", "checkbox"}:
                choices: List[Dict[str, Optional[str]]] = []
                lookup_xpath = (
                    f".//input[@type='{ctrl_type}' and "
                    f"(@name='{control_name}' or @id='{control_id}')]"
                )
                for option in panel.find_elements(By.XPATH, lookup_xpath):
                    choices.append(
                        {
                            "id": option.get_attribute("id") or None,
                            "value": option.get_attribute("value") or None,
                            "label": _get_label_for_control(option) or None,
                        }
                    )
                if choices:
                    field["choices"] = choices

            fields.append(field)

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(fields, handle, ensure_ascii=False, indent=2)

    print(
        f"Extraidos {len(fields)} campos visibles dentro de '{panel_selector}'. "
        f"Archivo creado: {output_path}"
    )
    return fields


if __name__ == "__main__":
    # Script de ejemplo: espera que ya tengas un `driver` autenticado y en el formulario.
    # from scraper import login_corfo
    # driver = login_corfo(...)
    # extract_form_to_json(driver, r\"c:\\ruta\\a\\formulario.json\")
    print(
        "Importa extract_form_to_json(driver, output_path) y llamalo una vez que el formulario este visible."
    )
