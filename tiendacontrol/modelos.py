"""Modelo de dominio de TiendaControl.

Cada clase implementa reglas de negocio de la Actividad 2 (RN-01 a RN-10).
Los errores de negocio se lanzan como excepciones propias para que la interfaz
muestre un mensaje claro y las pruebas puedan verificarlos.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Optional


def cop(valor: float) -> str:
    """Formato de pesos colombianos: $12.600"""
    return f"${valor:,.0f}".replace(",", ".")


# ----------------------------------------------------------------- Excepciones
class ErrorNegocio(Exception):
    """Error base: se viola una regla de negocio."""


class PermisoDenegado(ErrorNegocio):
    """El usuario no tiene el rol necesario (RN-04, CP-13)."""


class StockInsuficiente(ErrorNegocio):
    """Venta mayor a las existencias (RN-01)."""


class LimiteCreditoExcedido(ErrorNegocio):
    """Venta a crédito supera el límite del cliente (RN-07)."""


class AbonoInvalido(ErrorNegocio):
    """Abono no positivo o mayor al saldo (RN-08)."""


# --------------------------------------------------------------------- Usuario
class Usuario:
    """Persona que usa el sistema. Roles: 'propietario' o 'empleado'."""

    ROLES = ("propietario", "empleado")

    def __init__(self, nombre: str, rol: str, clave: str):
        if rol not in self.ROLES:
            raise ValueError(f"Rol inválido: {rol}")
        self.nombre = nombre
        self.rol = rol
        self._hash = self._cifrar(clave)

    @staticmethod
    def _cifrar(clave: str) -> str:
        return hashlib.sha256(clave.encode("utf-8")).hexdigest()

    def verificar_clave(self, clave: str) -> bool:
        return self._hash == self._cifrar(clave)

    @property
    def es_propietario(self) -> bool:
        return self.rol == "propietario"


# ------------------------------------------------------------------------ Lote
class Lote:
    """Tanda de un producto con su cantidad, costo y vencimiento (RN-02)."""

    _siguiente_id = 1

    def __init__(self, cantidad: int, costo_unitario: float,
                 vence: Optional[date] = None, ingreso: Optional[date] = None):
        self.id = Lote._siguiente_id
        Lote._siguiente_id += 1
        self.cantidad = cantidad
        self.costo_unitario = costo_unitario
        self.vence = vence
        self.ingreso = ingreso or date.today()

    def orden_de_salida(self):
        """Primero el que vence antes; sin vencimiento, el más antiguo."""
        return (self.vence is None, self.vence or date.max, self.ingreso, self.id)


# -------------------------------------------------------------------- Producto
class Producto:
    def __init__(self, codigo: str, nombre: str, categoria: str,
                 precio_venta: float, stock_minimo: int = 0):
        self.codigo = codigo
        self.nombre = nombre
        self.categoria = categoria
        self.precio_venta = precio_venta
        self.stock_minimo = stock_minimo
        self.costo_promedio = 0.0
        self.lotes: list[Lote] = []

    @property
    def existencias(self) -> int:
        return sum(l.cantidad for l in self.lotes)

    def registrar_entrada(self, cantidad: int, costo: float,
                          vence: Optional[date] = None,
                          ingreso: Optional[date] = None) -> Lote:
        """Crea un lote y recalcula el costo promedio ponderado (RN-06)."""
        if cantidad <= 0 or costo < 0:
            raise ErrorNegocio("Cantidad y costo deben ser válidos.")
        existentes = self.existencias
        self.costo_promedio = (
            (existentes * self.costo_promedio + cantidad * costo) / (existentes + cantidad)
        )
        lote = Lote(cantidad, costo, vence, ingreso)
        self.lotes.append(lote)
        return lote

    def descontar(self, cantidad: int) -> list[tuple[Lote, int]]:
        """Descuenta por la regla RN-02 y devuelve qué se tomó de cada lote."""
        if cantidad <= 0:
            raise ErrorNegocio("La cantidad debe ser mayor a cero.")
        if cantidad > self.existencias:
            raise StockInsuficiente(
                f"No hay suficientes existencias de {self.nombre}: "
                f"disponibles {self.existencias}, solicitadas {cantidad}."
            )
        pendiente = cantidad
        consumos: list[tuple[Lote, int]] = []
        for lote in sorted(self.lotes, key=Lote.orden_de_salida):
            if pendiente == 0:
                break
            tomar = min(lote.cantidad, pendiente)
            if tomar > 0:
                lote.cantidad -= tomar
                pendiente -= tomar
                consumos.append((lote, tomar))
        return consumos

    def restituir(self, consumos: list[tuple[Lote, int]]) -> None:
        for lote, cantidad in consumos:
            lote.cantidad += cantidad

    def por_agotarse(self) -> bool:
        return self.existencias <= self.stock_minimo

    def lotes_por_vencer(self, dias: int = 30, hoy: Optional[date] = None) -> list[Lote]:
        hoy = hoy or date.today()
        limite = hoy + timedelta(days=dias)
        return [l for l in self.lotes if l.cantidad > 0 and l.vence and l.vence <= limite]


# ----------------------------------------------------------------------- Deuda
class Deuda:
    def __init__(self, venta_id: int, fecha: date, monto: float):
        self.venta_id = venta_id
        self.fecha = fecha
        self.monto = monto
        self.pendiente = monto


# --------------------------------------------------------------------- Cliente
class Cliente:
    def __init__(self, nombre: str, limite_credito: float = 0, plazo_dias: int = 30):
        self.nombre = nombre
        self.limite_credito = limite_credito  # RN-07: cero = sin fiado
        self.plazo_dias = plazo_dias          # RN-09: 30 por defecto
        self.deudas: list[Deuda] = []

    @property
    def saldo(self) -> float:
        return sum(d.pendiente for d in self.deudas)

    def excede_limite(self, monto: float) -> bool:
        return self.saldo + monto > self.limite_credito

    def registrar_deuda(self, venta_id: int, fecha: date, monto: float) -> None:
        self.deudas.append(Deuda(venta_id, fecha, monto))

    def abonar(self, monto: float) -> list[tuple[int, float]]:
        """RN-08: aplica el abono a la deuda más antigua primero."""
        if monto <= 0:
            raise AbonoInvalido("El abono debe ser mayor a cero.")
        if monto > self.saldo:
            raise AbonoInvalido(f"El abono supera el saldo del cliente ({cop(self.saldo)}).")
        restante, aplicado = monto, []
        for deuda in sorted(self.deudas, key=lambda d: d.fecha):
            if restante == 0:
                break
            if deuda.pendiente > 0:
                pago = min(deuda.pendiente, restante)
                deuda.pendiente -= pago
                restante -= pago
                aplicado.append((deuda.venta_id, pago))
        return aplicado

    def antiguedad(self, hoy: Optional[date] = None) -> dict[str, float]:
        """RN-09: agrupa lo adeudado por antigüedad (0-30, 31-60, más de 60 días)."""
        hoy = hoy or date.today()
        rangos = {"0 a 30 días": 0.0, "31 a 60 días": 0.0, "Más de 60 días": 0.0}
        for d in self.deudas:
            if d.pendiente <= 0:
                continue
            dias = (hoy - d.fecha).days
            clave = "0 a 30 días" if dias <= 30 else "31 a 60 días" if dias <= 60 else "Más de 60 días"
            rangos[clave] += d.pendiente
        return rangos

    def deuda_vencida(self, hoy: Optional[date] = None) -> float:
        hoy = hoy or date.today()
        return sum(d.pendiente for d in self.deudas
                   if d.pendiente > 0 and (hoy - d.fecha).days > self.plazo_dias)


# ----------------------------------------------------------------------- Venta
class LineaVenta:
    def __init__(self, producto: Producto, cantidad: int, precio: float,
                 costo: float, consumos: list[tuple[Lote, int]]):
        self.producto = producto
        self.cantidad = cantidad
        self.precio_unitario = precio
        self.costo_unitario = costo   # RN-06: el costo vigente se guarda en la venta
        self.consumos = consumos

    @property
    def subtotal(self) -> float:
        return self.cantidad * self.precio_unitario

    @property
    def utilidad(self) -> float:
        return self.cantidad * (self.precio_unitario - self.costo_unitario)


class Venta:
    def __init__(self, id_: int, fecha: date, usuario: Usuario, tipo: str,
                 cliente: Optional[Cliente], lineas: list[LineaVenta]):
        self.id = id_
        self.fecha = fecha
        self.usuario = usuario
        self.tipo = tipo              # 'contado' o 'credito'
        self.cliente = cliente
        self.lineas = lineas
        self.anulada = False
        self.motivo_anulacion = ""

    @property
    def total(self) -> float:
        return sum(l.subtotal for l in self.lineas)

    @property
    def utilidad(self) -> float:
        return sum(l.utilidad for l in self.lineas)


# ------------------------------------------------------------------ Inventario
class Inventario:
    """Servicio principal: reúne productos, clientes, ventas y bitácora."""

    def __init__(self):
        self.productos: dict[str, Producto] = {}
        self.clientes: dict[str, Cliente] = {}
        self.ventas: list[Venta] = []
        self.bitacora: list[str] = []
        self.perdidas: list[dict] = []
        self._ventas_id = 1

    # -- utilidades
    def _registrar(self, usuario: Usuario, accion: str) -> None:
        self.bitacora.append(f"{date.today()} | {usuario.nombre} ({usuario.rol}) | {accion}")

    @staticmethod
    def _exigir_propietario(usuario: Usuario) -> None:
        if not usuario.es_propietario:
            raise PermisoDenegado("Esta acción es solo para el propietario.")

    # -- catálogo
    def agregar_producto(self, p: Producto) -> None:
        self.productos[p.codigo] = p

    def agregar_cliente(self, c: Cliente) -> None:
        self.clientes[c.nombre] = c

    # -- ventas (RN-01, RN-02, RN-06, RN-07)
    def registrar_venta(self, usuario: Usuario, items: list[tuple[str, int]],
                        tipo: str = "contado", cliente: Optional[str] = None,
                        autoriza: Optional[Usuario] = None) -> Venta:
        if not items:
            raise ErrorNegocio("La venta debe tener al menos un producto.")
        # 1) validar todo antes de modificar nada
        pedidos: dict[str, int] = {}
        for codigo, cantidad in items:
            pedidos[codigo] = pedidos.get(codigo, 0) + cantidad
        for codigo, cantidad in pedidos.items():
            prod = self.productos[codigo]
            if cantidad <= 0:
                raise ErrorNegocio("La cantidad debe ser mayor a cero.")
            if cantidad > prod.existencias:
                raise StockInsuficiente(
                    f"No hay suficientes existencias de {prod.nombre}: "
                    f"disponibles {prod.existencias}, solicitadas {cantidad}."
                )
        total = sum(self.productos[c].precio_venta * q for c, q in pedidos.items())
        cli = None
        if tipo == "credito":
            if not cliente or cliente not in self.clientes:
                raise ErrorNegocio("Una venta a crédito requiere un cliente registrado.")
            cli = self.clientes[cliente]
            if cli.excede_limite(total):
                if not (autoriza and autoriza.es_propietario):
                    raise LimiteCreditoExcedido(
                        f"La venta de {cop(total)} supera el límite de crédito de {cli.nombre} "
                        f"(saldo {cop(cli.saldo)}, límite {cop(cli.limite_credito)}). "
                        "Requiere autorización del propietario."
                    )
                self._registrar(autoriza, f"Autorizó crédito sobre el límite a {cli.nombre}")
        # 2) ejecutar
        lineas = []
        for codigo, cantidad in pedidos.items():
            prod = self.productos[codigo]
            costo = prod.costo_promedio
            consumos = prod.descontar(cantidad)
            lineas.append(LineaVenta(prod, cantidad, prod.precio_venta, costo, consumos))
        venta = Venta(self._ventas_id, date.today(), usuario, tipo, cli, lineas)
        self._ventas_id += 1
        self.ventas.append(venta)
        if cli:
            cli.registrar_deuda(venta.id, venta.fecha, venta.total)
        self._registrar(usuario, f"Venta #{venta.id} ({tipo}) por {cop(venta.total)}")
        return venta

    # -- anulaciones (RN-04)
    def anular_venta(self, usuario: Usuario, venta_id: int, motivo: str) -> Venta:
        self._exigir_propietario(usuario)
        if not motivo.strip():
            raise ErrorNegocio("La anulación requiere un motivo.")
        venta = next((v for v in self.ventas if v.id == venta_id), None)
        if venta is None or venta.anulada:
            raise ErrorNegocio("La venta no existe o ya está anulada.")
        if venta.cliente:
            deuda = next(d for d in venta.cliente.deudas if d.venta_id == venta.id)
            if deuda.pendiente != deuda.monto:
                raise ErrorNegocio("No se puede anular una venta a crédito que ya tiene abonos.")
            deuda.pendiente = 0
        for linea in venta.lineas:
            linea.producto.restituir(linea.consumos)
        venta.anulada, venta.motivo_anulacion = True, motivo
        self._registrar(usuario, f"Anuló la venta #{venta.id}: {motivo}")
        return venta

    # -- bajas (RN-05)
    def dar_de_baja(self, usuario: Usuario, codigo: str, lote_id: int,
                    cantidad: int, motivo: str) -> None:
        self._exigir_propietario(usuario)
        prod = self.productos[codigo]
        lote = next((l for l in prod.lotes if l.id == lote_id), None)
        if lote is None or cantidad <= 0 or cantidad > lote.cantidad or not motivo.strip():
            raise ErrorNegocio("Baja inválida: revise lote, cantidad y motivo.")
        lote.cantidad -= cantidad
        valor = cantidad * lote.costo_unitario
        self.perdidas.append({"fecha": date.today(), "producto": prod.nombre,
                              "cantidad": cantidad, "motivo": motivo, "valor": valor})
        self._registrar(usuario, f"Baja de {cantidad} {prod.nombre}: {motivo}")

    # -- abonos (RN-08)
    def registrar_abono(self, usuario: Usuario, cliente: str, monto: float):
        aplicado = self.clientes[cliente].abonar(monto)
        self._registrar(usuario, f"Abono de {cop(monto)} de {cliente}")
        return aplicado

    # -- reportes y alertas
    def productos_por_agotarse(self) -> list[Producto]:
        return [p for p in self.productos.values() if p.por_agotarse()]

    def lotes_por_vencer(self, dias: int = 30) -> list[tuple[Producto, Lote]]:
        return [(p, l) for p in self.productos.values() for l in p.lotes_por_vencer(dias)]

    def reporte_utilidad(self, usuario: Usuario) -> dict:
        """CP-13: solo el propietario ve costos y utilidad."""
        self._exigir_propietario(usuario)
        validas = [v for v in self.ventas if not v.anulada]
        return {
            "ventas": sum(v.total for v in validas),
            "utilidad": sum(v.utilidad for v in validas),
            "perdidas": sum(p["valor"] for p in self.perdidas),
        }

    def cartera(self) -> list[dict]:
        return [{"cliente": c.nombre, "saldo": c.saldo, "vencida": c.deuda_vencida(),
                 "limite": c.limite_credito}
                for c in self.clientes.values() if c.saldo > 0]
