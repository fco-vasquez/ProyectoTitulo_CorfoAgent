import time
import getpass
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
from selenium.common.exceptions import (
    ElementNotInteractableException,
    TimeoutException,
    NoSuchElementException,
)
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://login.corfo.cl/gsi/login/Login.aspx?uid=WEB226&env=produccion-cloud&enforcelogin=1&cid=2629"

def login_corfo(rut: str, clave: str, headless: bool = False, wait_seconds: int = 20):
    options = webdriver.ChromeOptions()
    # Evitar mensajes en la consola en Windows
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, wait_seconds)

    try:
        driver.get(URL)

        # 1) Hacer clic en el enlace que muestra el formulario de login (mostrarCorfoLoginLink)
        try:
            mostrar_link = wait.until(EC.presence_of_element_located((By.ID, "mostrarCorfoLoginLink")))
        except TimeoutException:
            raise RuntimeError("No se encontró el enlace mostrarCorfoLoginLink en la página.")

        # Intentos seguros de click: click normal -> ActionChains -> JS click -> llamar a la función JS
        clicked = False
        try:
            mostrar_link.click()
            clicked = True
            print("Click directo sobre mostrarCorfoLoginLink realizado.")
        except ElementNotInteractableException:
            print("Elemento presente pero no interactuable con click directo, intentando ActionChains...")
            try:
                ActionChains(driver).move_to_element(mostrar_link).click().perform()
                clicked = True
                print("ActionChains click realizado.")
            except Exception:
                print("ActionChains falló, intentando click vía JavaScript...")
        except Exception as e:
            print("Error en click directo:", e)

        if not clicked:
            try:
                driver.execute_script("document.getElementById('mostrarCorfoLoginLink').click();")
                clicked = True
                print("Click ejecutado vía document.getElementById(...).click()")
            except Exception as e:
                print("JS click falló:", e)

        if not clicked:
            # como último recurso, invocar la función JS que el enlace llama
            try:
                driver.execute_script("if (typeof mostrarCorfoLogin === 'function') { mostrarCorfoLogin(); }")
                clicked = True
                print("Se llamó a mostrarCorfoLogin() vía JS.")
            except Exception as e:
                print("Llamada a mostrarCorfoLogin() falló:", e)

        if not clicked:
            raise RuntimeError("No fue posible activar el enlace para mostrar el formulario de login.")

        # 2) Esperar los campos y rellenar rut y clave
        try:
            rut_field = wait.until(EC.visibility_of_element_located((By.ID, "rut")))
            rut_field.clear()
            rut_field.send_keys(rut)
        except TimeoutException:
            raise RuntimeError("No se encontró el campo 'rut' tras mostrar el formulario.")

        try:
            pass_field = wait.until(EC.visibility_of_element_located((By.ID, "pass")))
            pass_field.clear()
            pass_field.send_keys(clave)
        except TimeoutException:
            raise RuntimeError("No se encontró el campo 'pass' tras mostrar el formulario.")

        # 3) Pulsar el botón 'Enviar' (id="ingresa_") — es type="button" con onclick="validaIngreso();"
        clicked_send = False
        try:
            # esperar que el botón sea clickable (visibilidad + enabled)
            send_btn = wait.until(EC.element_to_be_clickable((By.ID, "ingresa_")))
            try:
                send_btn.click()
                clicked_send = True
                print("Click directo sobre el botón Enviar (ingresa_) realizado.")
            except ElementNotInteractableException:
                print("Botón no interactuable con click directo, intentando ActionChains...")
                try:
                    ActionChains(driver).move_to_element(send_btn).click().perform()
                    clicked_send = True
                    print("ActionChains click sobre Enviar realizado.")
                except Exception:
                    print("ActionChains falló para Enviar, intentando JS click...")
            except Exception as e:
                print("Error al hacer click directo en Enviar:", e)
        except TimeoutException:
            print("No se encontró el botón 'ingresa_' como clickable.")

        if not clicked_send:
            # Fallback: click vía JS sobre el elemento (si existe)
            try:
                el = driver.find_element(By.ID, "ingresa_")
                driver.execute_script("arguments[0].click();", el)
                clicked_send = True
                print("Click vía JS ejecutado sobre el botón Enviar.")
            except Exception as e:
                print("Click vía JS sobre el botón Enviar falló:", e)

        if not clicked_send:
            # Último recurso: llamar directamente a la función JS que valida/envía
            try:
                driver.execute_script("if (typeof validaIngreso === 'function') { validaIngreso(); }")
                clicked_send = True
                print("Se llamó a validaIngreso() vía JS.")
            except Exception as e:
                print("Llamada a validaIngreso() falló:", e)

        if not clicked_send:
            raise RuntimeError("No fue posible activar el envío del formulario (botón Enviar).")

        # 4) Esperar un cambio de URL o un elemento que indique sesión iniciada (ajusta si conoces uno)
        # Esperar al menos 30 segundos para que cargue la página siguiente antes de interactuar
        print("Esperando 15 segundos para la carga post-login...")
        time.sleep(15)
        current = driver.current_url
        title = driver.title
        print(f"Login ejecutado (URL actual: {current} | título: {title})")

        # 5) Después del login: puede aparecer el botón "Nueva Postulación +" o la barra de pasos (#BarraPasosContenedor).
        try:
            nueva_xpath = ("//span[contains(@class,'btn') and contains(@class,'btn-primary') "
                           "and contains(@class,'btn-xs') and contains(normalize-space(.),'Nueva Postulación')]")

            # esperar hasta que aparezca cualquiera de los dos elementos (timeout = wait_seconds)
            def either_present(driver):
                if driver.find_elements(By.XPATH, nueva_xpath):
                    return "nueva"
                if driver.find_elements(By.ID, "BarraPasosContenedor"):
                    return "barra"
                return False

            found = WebDriverWait(driver, wait_seconds).until(either_present)

            if found == "nueva":
                # click sobre "Nueva Postulación +"
                new_btn = driver.find_element(By.XPATH, nueva_xpath)
                clicked_new = False
                try:
                    new_btn.click()
                    clicked_new = True
                    print("Click directo sobre 'Nueva Postulación +' realizado.")
                except ElementNotInteractableException:
                    try:
                        ActionChains(driver).move_to_element(new_btn).click().perform()
                        clicked_new = True
                        print("ActionChains click sobre 'Nueva Postulación +' realizado.")
                    except Exception:
                        pass

                if not clicked_new:
                    try:
                        driver.execute_script("arguments[0].click();", new_btn)
                        clicked_new = True
                        print("Click vía JS sobre 'Nueva Postulación +' realizado.")
                    except Exception as e:
                        print("Click vía JS sobre 'Nueva Postulación +' falló:", e)

                if not clicked_new:
                    # último recurso: buscar por texto simple y hacer click vía JS
                    try:
                        el_text = driver.find_element(By.XPATH, "//span[contains(normalize-space(.),'Nueva Postulación')]")
                        driver.execute_script("arguments[0].click();", el_text)
                        clicked_new = True
                        print("Click vía JS sobre elemento encontrado por texto 'Nueva Postulación'.")
                    except Exception as e:
                        print("No fue posible activar 'Nueva Postulación +':", e)

            elif found == "barra":
                # si aparece la barra, intentar clicar el paso activo (o el primer BotonPaso)
                clicked_step = False
                try:
                    # intentar elemento activo primero
                    active_xpath = ("//div[@id='BarraPasosContenedor']//span[contains(@class,'BotonPaso') "
                                    "and contains(@class,'activo')]")
                    step = None
                    elems = driver.find_elements(By.XPATH, active_xpath)
                    if elems:
                        step = elems[0]
                    else:
                        # fallback: el primer BotonPaso dentro de la barra
                        elems2 = driver.find_elements(By.XPATH, "//div[@id='BarraPasosContenedor']//span[contains(@class,'BotonPaso')]")
                        if elems2:
                            step = elems2[0]

                    if not step:
                        raise RuntimeError("No se encontró ningún BotonPaso en BarraPasosContenedor.")

                    try:
                        step.click()
                        clicked_step = True
                        print("Click directo sobre BotonPaso realizado.")
                    except ElementNotInteractableException:
                        try:
                            ActionChains(driver).move_to_element(step).click().perform()
                            clicked_step = True
                            print("ActionChains click sobre BotonPaso realizado.")
                        except Exception:
                            pass

                    if not clicked_step:
                        try:
                            driver.execute_script("arguments[0].click();", step)
                            clicked_step = True
                            print("Click vía JS sobre BotonPaso realizado.")
                        except Exception as e:
                            print("Click vía JS sobre BotonPaso falló:", e)

                    if not clicked_step:
                        raise RuntimeError("No fue posible activar ningún BotonPaso en la barra.")

                except Exception as e:
                    print("Error al manejar BarraPasosContenedor:", e)

        except TimeoutException:
            print("No apareció ni 'Nueva Postulación +' ni la barra de pasos dentro del timeout.")

        return driver  # devuelve el driver para que el llamador decida cuándo cerrarlo

    except Exception as e:
        # No cerramos el driver aquí para permitir inspección en caso de error
        print("Error durante el proceso de login:", e)
        raise

if __name__ == "__main__":
    print("Inicio de sesión en Corfo (se abrirá Chrome).")
    rut_input = input("Ingrese RUT (ej. 12.345.678-9): ").strip()
    clave_input = getpass.getpass("Ingrese clave: ")

    driver = None
    try:
        # Por seguridad, evita headless mientras desarrollas para ver la interacción
        driver = login_corfo(rut_input, clave_input, headless=False)
        print("Login ejecutado. Revisa la ventana del navegador.")
        input("Presiona ENTER para cerrar el navegador y terminar el script...")
    except Exception as e:
        print("Ocurrió un error:", e)
        if driver:
            input("Se dejó el navegador abierto para inspección. Presiona ENTER para cerrarlo...")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass