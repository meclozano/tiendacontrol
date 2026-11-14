# TiendaControl (prototipo funcional)
Link: https://tiendacontrol-elvira.streamlit.app/

Sistema web de gestión de inventarios y ventas para tiendas de barrio de Melgar, Tolima.
Proyecto de software · Corporación Universitaria Iberoamericana · Actividad 4.

## Tecnologías
Python 3.10+ (programación orientada a objetos), Streamlit (interfaz web), unittest (pruebas).

## Instalación y ejecución
```bash
git clone https://github.com/meclozano/tiendacontrol.git
cd tiendacontrol
pip install -r requirements.txt
streamlit run app.py
```
Abre http://localhost:8501. Usuarios de prueba: `dueno / 1234` (propietario) y `empleado / abcd`.

## Pruebas de aceptación
```bash
python -m unittest discover -s tests -v
```

## Estructura
- `tiendacontrol/modelos.py`: clases Usuario, Lote, Producto, Deuda, Cliente, LineaVenta, Venta e Inventario.
- `tests/`: una prueba por criterio de aceptación (CP-xx).
- `app.py`: interfaz Streamlit.
- `docs/`: documento de la actividad y manual técnico.

## Fuera del prototipo (siguiente iteración)
Compras a proveedores y cuentas por pagar, devoluciones, sincronización sin conexión (RN-11) y persistencia en base de datos.
