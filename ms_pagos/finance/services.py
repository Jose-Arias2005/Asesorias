from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import Wallet, Transaction

def create_wallet(user_id):
    """
    Crea una billetera para un usuario nuevo.
    Idempotente: Si ya existe, retorna la existente.
    """
    wallet, _ = Wallet.objects.get_or_create(user_id=user_id)
    return wallet

def execute_transaction(user_id, amount, type, payment_method=None, reference=None, source=None, description=None, extra_info=None):
    """
    Función MAESTRA actualizada.
    Ahora soporta info flexible y métodos de pago.
    """
    amount = Decimal(amount)
    if extra_info is None:
        extra_info = {}
    
    # Default payment method si no se especifica
    if not payment_method:
        payment_method = Transaction.PaymentMethod.BALANCE
    
    with transaction.atomic():
        try:
            wallet = Wallet.objects.select_for_update().get(user_id=user_id)
        except Wallet.DoesNotExist:
            raise ValidationError(f"Billetera no encontrada para usuario {user_id}")
        
        # Validar Fondos (Solo si es salida y NO es un sobregiro permitido)
        if amount < 0 and wallet.balance < abs(amount):
            raise ValidationError(f"Saldo insuficiente. Tienes {wallet.balance}")
            
        if not wallet.is_active:
            raise ValidationError("La billetera está congelada")

        # Ejecutar movimiento
        wallet.balance += amount
        wallet.save()
        
        # Registrar Transacción
        trx = Transaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type=type,
            payment_method=payment_method,
            status=Transaction.TransactionStatus.COMPLETED,
            external_reference=reference,
            reference_source=source,
            description=description,
            info=extra_info
        )
        
        return trx