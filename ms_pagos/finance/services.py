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

def execute_recharge(user_id, amount, payment_method):
    """
    Recarga saldo a una billetera (Entrada de dinero).
    """
    if amount <= 0:
        raise ValidationError("El monto de recarga debe ser positivo")

    with transaction.atomic():
        # Bloqueamos la fila de la billetera (select_for_update)
        wallet = Wallet.objects.select_for_update().get(user_id=user_id)
        
        wallet.balance += Decimal(amount)
        wallet.save()
        
        # Creamos el registro histórico
        trx = Transaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type=Transaction.TransactionType.RECHARGE,
            status=Transaction.TransactionStatus.COMPLETED,
            payment_method=payment_method
        )
        
        return trx

def execute_payment(user_id, amount, booking_id=None):
    """
    Cobra una clase (Salida de dinero).
    Retorna la transacción creada.
    """
    if amount <= 0:
        raise ValidationError("El monto a pagar debe ser positivo")

    with transaction.atomic():
        try:
            wallet = Wallet.objects.select_for_update().get(user_id=user_id)
        except Wallet.DoesNotExist:
            raise ValidationError(f"El usuario {user_id} no tiene billetera")

        if wallet.balance < amount:
            raise ValidationError("Saldo insuficiente")

        # Descuento:
        wallet.balance -= Decimal(amount)
        wallet.save()

        # Crear transacción
        trx = Transaction.objects.create(
            wallet=wallet,
            amount=-amount, # Negativo en el historial para indicar salida
            transaction_type=Transaction.TransactionType.PAYMENT,
            status=Transaction.TransactionStatus.COMPLETED,
            payment_method=Transaction.PaymentMethod.INTERNAL
        )
        
        # TODO:
        # NOTA: Aquí falta crear el PaymentDetail, pero eso lo haremos
        # cuando conectemos con el microservicio de Reservas.
        
        return trx