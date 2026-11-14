"""Cada prueba corresponde a un criterio de aceptación (CP-xx) del documento."""
import unittest
from datetime import date, timedelta

from tiendacontrol import (Usuario, Producto, Cliente, Inventario, PermisoDenegado,
                           StockInsuficiente, LimiteCreditoExcedido, AbonoInvalido)


def tienda():
    inv = Inventario()
    dueno = Usuario("Doña Rosa", "propietario", "1234")
    emp = Usuario("Carlos", "empleado", "abcd")
    return inv, dueno, emp


class TestCriterios(unittest.TestCase):
    def test_hu01_login_y_roles(self):
        _, dueno, emp = tienda()
        self.assertTrue(dueno.verificar_clave("1234"))
        self.assertFalse(dueno.verificar_clave("0000"))
        self.assertTrue(dueno.es_propietario)
        self.assertFalse(emp.es_propietario)

    def test_cp13_empleado_no_ve_costos_ni_utilidad(self):
        inv, dueno, emp = tienda()
        with self.assertRaises(PermisoDenegado):
            inv.reporte_utilidad(emp)
        self.assertIn("utilidad", inv.reporte_utilidad(dueno))

    def test_cp01_venta_mayor_a_existencias_se_rechaza(self):
        inv, dueno, emp = tienda()
        p = Producto("P1", "Arroz", "Granos", 3000, 2)
        p.registrar_entrada(5, 2000)
        inv.agregar_producto(p)
        with self.assertRaises(StockInsuficiente):
            inv.registrar_venta(emp, [("P1", 6)])
        self.assertEqual(p.existencias, 5)

    def test_cp02_se_descuenta_primero_el_lote_que_vence_antes(self):
        inv, dueno, emp = tienda()
        p = Producto("P2", "Leche", "Lácteos", 4000, 2)
        l20 = p.registrar_entrada(10, 3000, vence=date(2027, 1, 20))
        l10 = p.registrar_entrada(10, 3000, vence=date(2027, 1, 10))
        inv.agregar_producto(p)
        inv.registrar_venta(emp, [("P2", 14)])
        self.assertEqual(l10.cantidad, 0)
        self.assertEqual(l20.cantidad, 6)
        self.assertEqual(p.existencias, 6)

    def test_cp04_solo_el_propietario_anula_y_restaura_existencias(self):
        inv, dueno, emp = tienda()
        p = Producto("P3", "Aceite", "Despensa", 9000, 1)
        p.registrar_entrada(10, 7000)
        inv.agregar_producto(p)
        v = inv.registrar_venta(emp, [("P3", 4)])
        self.assertEqual(p.existencias, 6)
        with self.assertRaises(PermisoDenegado):
            inv.anular_venta(emp, v.id, "error")
        inv.anular_venta(dueno, v.id, "error de digitación")
        self.assertEqual(p.existencias, 10)
        self.assertTrue(v.anulada)

    def test_cp05_baja_por_vencimiento_registra_perdida(self):
        inv, dueno, emp = tienda()
        p = Producto("P4", "Yogurt", "Lácteos", 2500, 1)
        lote = p.registrar_entrada(10, 1500, vence=date.today() - timedelta(days=1))
        inv.agregar_producto(p)
        inv.dar_de_baja(dueno, "P4", lote.id, 2, "vencido")
        self.assertEqual(lote.cantidad, 8)
        self.assertEqual(inv.reporte_utilidad(dueno)["perdidas"], 3000)

    def test_cp06_costo_promedio_y_utilidad(self):
        inv, dueno, emp = tienda()
        p = Producto("P5", "Gaseosa", "Bebidas", 3000, 5)
        p.registrar_entrada(10, 2000)
        p.registrar_entrada(20, 2300)
        inv.agregar_producto(p)
        self.assertEqual(round(p.costo_promedio), 2200)
        v = inv.registrar_venta(dueno, [("P5", 1)])
        self.assertEqual(round(v.utilidad), 800)

    def test_cp07_credito_sobre_el_limite_se_rechaza_salvo_autorizacion(self):
        inv, dueno, emp = tienda()
        p = Producto("P6", "Huevos", "Básicos", 15000, 1)
        p.registrar_entrada(10, 10000)
        inv.agregar_producto(p)
        inv.agregar_cliente(Cliente("Ana", limite_credito=50000))
        inv.clientes["Ana"].registrar_deuda(0, date.today(), 40000)
        with self.assertRaises(LimiteCreditoExcedido):
            inv.registrar_venta(emp, [("P6", 1)], "credito", "Ana")
        with self.assertRaises(LimiteCreditoExcedido):
            inv.registrar_venta(emp, [("P6", 1)], "credito", "Ana", autoriza=emp)
        inv.registrar_venta(emp, [("P6", 1)], "credito", "Ana", autoriza=dueno)
        self.assertEqual(inv.clientes["Ana"].saldo, 55000)

    def test_cp08_abonos_aplican_a_la_deuda_mas_antigua(self):
        c = Cliente("Luis", limite_credito=100000)
        c.registrar_deuda(1, date.today() - timedelta(days=20), 30000)
        c.registrar_deuda(2, date.today() - timedelta(days=5), 20000)
        c.abonar(35000)
        self.assertEqual([d.pendiente for d in c.deudas], [0, 15000])
        with self.assertRaises(AbonoInvalido):
            c.abonar(100000)

    def test_cp09_deuda_de_35_dias_aparece_vencida_en_31_a_60(self):
        c = Cliente("Marta", limite_credito=100000, plazo_dias=30)
        c.registrar_deuda(1, date.today() - timedelta(days=35), 10000)
        self.assertEqual(c.deuda_vencida(), 10000)
        self.assertEqual(c.antiguedad()["31 a 60 días"], 10000)

    def test_hu02_alertas_por_agotarse_y_por_vencer(self):
        inv, dueno, emp = tienda()
        p = Producto("P7", "Pan", "Panadería", 500, 10)
        p.registrar_entrada(8, 300, vence=date.today() + timedelta(days=5))
        inv.agregar_producto(p)
        self.assertIn(p, inv.productos_por_agotarse())
        self.assertEqual(len(inv.lotes_por_vencer(30)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
