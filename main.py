import argparse
import getpass
from pathlib import Path
from typing import Optional

from scraper import login_corfo
from scraper_formulario import extract_form_to_json


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inicia sesión en la plataforma Corfo, abre un formulario y extrae "
            "los campos visibles dentro de los paneles del formulario."
        )
    )
    parser.add_argument(
        "--rut",
        help="RUT para iniciar sesión. Si no se entrega se solicitará por consola.",
    )
    parser.add_argument(
        "--password",
        help="Clave de acceso. Si no se entrega se solicitará de forma segura.",
    )
    parser.add_argument(
        "--output",
        default="formulario.json",
        help="Ruta del archivo JSON de salida (por defecto formulario.json).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecuta el navegador en modo headless (sin ventana visible).",
    )
    parser.add_argument(
        "--login-wait",
        type=int,
        default=20,
        help="Segundos máximos de espera para cada paso del login (default: 20).",
    )
    parser.add_argument(
        "--form-wait",
        type=int,
        default=30,
        help="Segundos máximos de espera para que el formulario termine de cargar (default: 30).",
    )
    parser.add_argument(
        "--panel-selector",
        default="div.panel-body",
        help="Selector CSS que identifica los paneles con los campos del formulario.",
    )
    parser.add_argument(
        "--auto-close",
        action="store_true",
        help="Cierra el navegador automáticamente al finalizar (por defecto se espera confirmación).",
    )
    return parser.parse_args()


def _prompt_rut(default: Optional[str] = None) -> str:
    prompt = "Ingrese RUT (ej. 12.345.678-9): "
    return (default or input(prompt)).strip()


def _prompt_password(default: Optional[str] = None) -> str:
    if default:
        return default
    return getpass.getpass("Ingrese clave: ")


def main() -> None:
    args = _parse_args()

    rut = _prompt_rut(args.rut)
    password = _prompt_password(args.password)

    output_path = Path(args.output).expanduser().resolve()
    driver = None

    try:
        driver = login_corfo(
            rut=rut,
            clave=password,
            headless=args.headless,
            wait_seconds=args.login_wait,
        )
        print("Inicio de sesión exitoso. Extrayendo formulario…")

        fields = extract_form_to_json(
            driver=driver,
            output_path=str(output_path),
            wait_seconds=args.form_wait,
            panel_selector=args.panel_selector,
        )

        print(f"Campos extraídos: {len(fields)}")
        print(f"Archivo generado en: {output_path}")

    except Exception as exc:
        print(f"Ocurrió un error durante el proceso: {exc}")
        raise

    finally:
        if driver:
            if not args.auto_close:
                try:
                    input("Presiona ENTER cuando quieras cerrar el navegador...")
                except KeyboardInterrupt:
                    print("\nSe recibió Ctrl+C, cerrando el navegador.")
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
