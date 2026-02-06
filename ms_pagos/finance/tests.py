from django.test import TestCase

# Create your tests here.
from decimal import Decimal
from .models import Wallet, Transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

class WalletE2ETests(APITestCase):
    
    def setUp(self):
        """
        Configuración inicial antes de CADA test.
        Creamos un usuario con billetera y saldo inicial para pruebas de cobro.
        """
        self.user_id = "USER_TEST_001"
        self.wallet = Wallet.objects.create(user_id=self.user_id, balance=Decimal("100.00"))
        
        # URLs (Usamos los names definidos en urls.py)
        self.url_create = reverse('create_wallet')
        self.url_detail = reverse('get_wallet', args=[self.user_id])
        self.url_deposit = reverse('deposit')
        self.url_charge = reverse('charge')

    # --- TEST 1: CREAR BILLETERA (POST /api/wallet/) ---
    def test_create_wallet_endpoint(self):
        new_user = "USER_NEW_002"
        data = {"user_id": new_user}
        
        response = self.client.post(self.url_create, data, format='json')
        
        # Verificamos respuesta HTTP
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user_id'], new_user)
        self.assertEqual(float(response.data['balance']), 0.00) # Nace vacía
        
        # Verificamos persistencia en BD
        self.assertTrue(Wallet.objects.filter(user_id=new_user).exists())

    # --- TEST 2: VER SALDO (GET /api/wallet/{id}/) ---
    def test_get_wallet_details(self):
        response = self.client.get(self.url_detail)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user_id'], self.user_id)
        self.assertEqual(float(response.data['balance']), 100.00)

    # --- TEST 3: RECARGAR SALDO (POST /api/transaction/deposit/) ---
    def test_deposit_endpoint(self):
        """
        Simula una recarga por Yape
        """
        data = {
            "user_id": self.user_id,
            "amount": 50.00,
            "payment_method": "YAPE",
            "info": {"celular_origen": "999111222"} # Probamos el campo JSON
        }
        
        response = self.client.post(self.url_deposit, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['transaction_type'], 'RECARGA')
        
        # Verificamos que el saldo subió (100 + 50 = 150)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("150.00"))
        
        # Verificamos que se guardó la info extra
        last_trx = Transaction.objects.last()
        self.assertEqual(last_trx.info.get('celular_origen'), "999111222")

    # --- TEST 4: COBRAR (POST /api/transaction/charge/) ---
    def test_charge_endpoint_success(self):
        """
        Simula el cobro de una Reserva desde el Orquestador
        """
        data = {
            "user_id": self.user_id,
            "amount": 40.00,
            "type": "PAGO_RESERVA",
            "external_reference": "RESERVA-999", # ID externo clave
            "description": "Clase de Matemáticas"
        }
        
        response = self.client.post(self.url_charge, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verificamos que el saldo bajó (100 - 40 = 60)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("60.00"))
        
        # Verificamos que la transacción guardó la referencia externa
        last_trx = Transaction.objects.filter(transaction_type='PAGO_RESERVA').last()
        self.assertEqual(last_trx.external_reference, "RESERVA-999")
        self.assertEqual(last_trx.amount, Decimal("-40.00")) # Debe ser negativo

    # --- TEST 5: VALIDACIÓN DE FONDOS (Caso Borde) ---
    def test_charge_insufficient_funds(self):
        """
        Intenta cobrar más de lo que tiene
        """
        data = {
            "user_id": self.user_id,
            "amount": 500.00, # Tiene 100, pide 500
            "type": "RETIRO"
        }
        
        response = self.client.post(self.url_charge, data, format='json')
        
        # Debe fallar con 400 Bad Request
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # El saldo debe seguir intacto
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("100.00"))