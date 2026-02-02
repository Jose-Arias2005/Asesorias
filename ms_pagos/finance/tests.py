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


from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from .models import Wallet, Transaction

class WalletIntegrationTests(APITestCase):
    
    def setUp(self):
        # Preparamos el terreno: Creamos una billetera inicial
        self.user_id = "TEST001"
        self.wallet = Wallet.objects.create(user_id=self.user_id, balance=0)
        
        self.url_recharge = reverse('recharge') 
        self.url_pay = reverse('pay')

    def test_recharge_endpoint_success(self):
        """
        Prueba todo el flujo: HTTP -> URL -> Vista -> Serializer -> Servicio
        """
        data = {
            "user_id": self.user_id,
            "amount": 100.00,
            "payment_method": "YAPE"
        }

        # 2. El cliente hace el POST
        response = self.client.post(self.url_recharge, data, format='json')

        # 3. Validaciones de la Capa HTTP
        # ¿El código de estado es 200 OK?
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # ¿El JSON de respuesta tiene los datos correctos?
        self.assertEqual(response.data['status'], 'COMPLETADO')
        self.assertEqual(float(response.data['amount']), 100.00)

        # 4. Validaciones de la Base de Datos (Efecto real)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 100.00)

    def test_recharge_invalid_data(self):
        """
        Prueba que el Serializer detenga datos basura (Validation Error)
        """
        # Enviamos datos incompletos (falta amount)
        data = {
            "user_id": self.user_id,
            # "amount": falta esto a propósito
        }

        response = self.client.post(self.url_recharge, data, format='json')

        # Esperamos un 400 BAD REQUEST (El Serializer debió gritar)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Verificamos que el serializer reportó qué campo falta
        self.assertIn('amount', response.data)

    def test_payment_endpoint_insufficient_funds(self):
        """
        Prueba que la Vista capture el error lógico y devuelva error HTTP
        """
        # Intentamos cobrar 500 (Saldo actual es 0)
        data = {
            "user_id": self.user_id,
            "amount": 500.00
        }

        response = self.client.post(self.url_pay, data, format='json')

        # Esperamos un 400 porque no hay saldo
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Opcional: Verificar que el mensaje de error sea el correcto
        # (Esto asume que tu vista devuelve {"error": "..."})
        self.assertIn("error", response.data)