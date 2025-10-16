import json
import time
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver import ActionChains


def _get_label_for_control(ctrl) -> Optional[str]:
    """Return a human readable label for the control if possible.
    Busca en ancestros, elementos previos y por atributo for en el form.
    Si no encuentra una etiqueta "legible" devuelve None (evita usar id crudo).
    """
    find = ctrl.find_element
    # 1) label dentro del form-group más cercano
    try:
        label = find(
            By.XPATH,
            "./ancestor::div[contains(@class,'form-group')][1]//label[normalize-space(text())!=''][1]",
        )
        text = label.text.strip()
        if text:
            return text
    except Exception:
        pass

    # 2) etiqueta padre (p. ej. <label><input ...></label>)
    try:
        parent_label = find(By.XPATH, "./parent::label")
        text = parent_label.text.strip()
        if text:
            return text
    except Exception:
        pass

    # 3) label asociado por for en el formulario/ancestro (más fiable que buscar en descendientes)
    try:
        control_id = ctrl.get_attribute("id")
        if control_id:
            label = find(By.XPATH, f"./ancestor::form[1]//label[@for='{control_id}']")
            text = label.text.strip()
            if text:
                return text
    except Exception:
        pass

    # 4) label precedente inmediato en el DOM (puede estar fuera del form-group)
    try:
        label = find(By.XPATH, "./preceding::label[1]")
        text = label.text.strip()
        if text:
            return text
    except Exception:
        pass

    # 5) label descendiente (raro, pero por si el control contiene label internamente)
    try:
        label = find(By.XPATH, ".//label[normalize-space(text())!=''][1]")
        text = label.text.strip()
        if text:
            return text
    except Exception:
        pass

    # Fallback: placeholder o name, pero sólo si parecen legibles (contienen letras)
    placeholder = (ctrl.get_attribute("placeholder") or "").strip()
    if placeholder:
        return placeholder
    name = (ctrl.get_attribute("name") or "").strip()
    if name and re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", name):
        return name
    # No devolver id crudo como label para evitar nombres como "10917038_0"
    return None


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
    seen_fields: Set[Tuple[Optional[str], Optional[str], Optional[str], str]] = set()

    for panel_index, panel in enumerate(panels):
        try:
            if not panel.is_displayed():
                continue
        except Exception:
            continue

        # --- Intentar expandir secciones colapsables dentro del panel ---
        try:
            # buscar toggles/headers: enlaces/botones con data-toggle, elementos con aria-controls, y headings (h3)
            toggle_xpath = (
                ".//a[@data-toggle='collapse' or @aria-controls] | "
                ".//button[@data-toggle='collapse' or @aria-controls] | .//h3"
            )
            toggles = panel.find_elements(By.XPATH, toggle_xpath)

            # recorrer de forma estable: primero abrir los que estén cerrados y que no sean "Agregar +"
            for t in toggles:
                try:
                    if not t.is_displayed():
                        continue
                except Exception:
                    continue

                # si ya está expandido, no tocar; si está cerrado, abrir y esperar su contenido
                try:
                    _ensure_expanded(driver, t, timeout=5)
                except Exception:
                    # no fallar el scraping por un toggle problemático
                    pass

            # dar un pequeño tiempo para que todo el contenido cargue tras las aperturas
            time.sleep(10)

        except Exception:
            pass
        # ----------------------------------------------------------------

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

            # Evitar duplicados: tupla (id, name, nombre, tipo)
            key = (field.get("id"), field.get("name"), field.get("nombre"), field.get("tipo"))
            if key in seen_fields:
                continue
            seen_fields.add(key)

            fields.append(field)

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(fields, handle, ensure_ascii=False, indent=2)

    print(
        f"Extraidos {len(fields)} campos visibles dentro de '{panel_selector}'. "
        f"Archivo creado: {output_path}"
    )
    return fields


def _get_collapse_target(driver, toggle):
    """Intentar resolver el elemento collapsible asociado al toggle (data-target, href, aria-controls, next-sibling)."""
    sel = None
    try:
        tgt = (toggle.get_attribute("data-target") or "").strip()
        if not tgt:
            href = (toggle.get_attribute("href") or "").strip()
            if href and href.startswith("#"):
                tgt = href
        if not tgt:
            tgt = (toggle.get_attribute("aria-controls") or "").strip()
        if tgt:
            # normalizar '#id' a id sin '#'
            if tgt.startswith("#"):
                tgt = tgt[1:]
            try:
                el = driver.find_element(By.ID, tgt)
                return el
            except Exception:
                pass
    except Exception:
        pass

    # fallback: buscar un siguiente hermano con clases típicas de collapse/panel-body
    try:
        sib = toggle.find_element(By.XPATH, "following-sibling::*[1]")
        cls = (sib.get_attribute("class") or "").lower()
        if "collapse" in cls or "panel-collapse" in cls or "panel-body" in cls:
            return sib
    except Exception:
        pass

    return None


def _ensure_expanded(driver, toggle, timeout=5):
    """Asegura que la sección asociada al toggle esté expandida.
    - Si ya está expandida (aria-expanded true o target visible) no hace nada.
    - Si está cerrada, intenta abrirla mediante click (con fallback JS) y espera visibilidad.
    Devuelve True si la sección está visible tras la operación, False en caso contrario.
    """
    # evitar botones tipo "Agregar"
    t_id = (toggle.get_attribute("id") or "").lower()
    t_text = (toggle.text or "").strip().lower()
    if t_id.startswith("btnagregar") or "agregar" in t_text:
        return False

    # 1) Si tiene aria-expanded, respetar su valor (si es 'true' no tocar)
    aria = toggle.get_attribute("aria-expanded")
    if aria is not None:
        if aria.lower() in ("true", "1"):
            return True
    # 2) intentar resolver target y comprobar visibilidad
    target = _get_collapse_target(driver, toggle)
    if target is not None:
        try:
            if target.is_displayed():
                return True
        except Exception:
            pass

    # 3) si no está abierto, intentar abrir con prudencia
    try:
        # click normal
        toggle.click()
    except Exception:
        try:
            ActionChains(driver).move_to_element(toggle).click().perform()
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", toggle)
            except Exception:
                pass

    # 4) esperar que el objetivo (si existe) sea visible; si no hay objetivo, esperar un pequeño retraso
    if target is not None:
        try:
            WebDriverWait(driver, timeout).until(EC.visibility_of(target))
            return True
        except Exception:
            return False
    else:
        # si no hay target conocido, esperar un breve tiempo para que el DOM se actualice
        time.sleep(5)
        # si aria cambia a true, considerarlo éxito
        aria2 = toggle.get_attribute("aria-expanded")
        if aria2 and aria2.lower() in ("true", "1"):
            return True
        return False


if __name__ == "__main__":
    # Script de ejemplo: espera que ya tengas un `driver` autenticado y en el formulario.
    # from scraper import login_corfo
    # driver = login_corfo(...)
    # extract_form_to_json(driver, r\"c:\\ruta\\a\\formulario.json\")
    print(
        "Importa extract_form_to_json(driver, output_path) y llamalo una vez que el formulario este visible."
    )
