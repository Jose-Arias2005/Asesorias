from django.test import TestCase

# Create your tests here.
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import Wallet, Transaction
from .services import create_wallet, execute_recharge, execute_payment

class WalletServiceTests(TestCase):

    def setUp(self):
        self.user_id = "20231001"
        self.wallet = create_wallet(self.user_id)

    def test_recharge_increases_balance(self):
        """Prueba que la recarga suba el saldo"""
        execute_recharge(self.user_id, 50.00, "YAPE")
        
        # Refrescamos desde la BD
        self.wallet.refresh_from_db()
        
        # Verificamos
        self.assertEqual(self.wallet.balance, Decimal("50.00"))
        # Verificamos que se creó la transacción
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(Transaction.objects.first().transaction_type, 'RECARGA')

    def test_payment_decreases_balance(self):
        """Prueba que el pago descuente correctamente"""
        # Primero le damos dinero (Setup)
        self.wallet.balance = Decimal("100.00")
        self.wallet.save()

        # Ejecutamos pago
        execute_payment(self.user_id, 40.00)
        
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("60.00"))

    def test_cannot_pay_insufficient_funds(self):
        """Prueba CRÍTICA: No se debe poder pagar si no hay saldo"""
        self.wallet.balance = Decimal("10.00")
        self.wallet.save()

        # Intentamos pagar 50 (debería lanzar error)
        with self.assertRaises(ValidationError):
            execute_payment(self.user_id, 50.00)
            
        # Aseguramos que el saldo NO cambió
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("10.00"))

    def test_cannot_transact_negative_amounts(self):
        """No permitir recargas ni pagos negativos"""
        with self.assertRaises(ValidationError):
            execute_recharge(self.user_id, -50.00, "YAPE")