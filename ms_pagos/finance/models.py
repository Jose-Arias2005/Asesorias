from django.db import models

# Create your models here.

from django.db import models
from django.utils.translation import gettext_lazy as _

class Wallet(models.Model):
    # Formato del user_id: <periodo><numero de 4 digitos>. ej: 202110001
    user_id = models.CharField(
        max_length=20, 
        unique=True, 
        db_index=True, 
        verbose_name="Student Code"
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet {self.user_id} - S/ {self.balance}"

class Transaction(models.Model):
    class TransactionType(models.TextChoices):
        RECHARGE = 'RECARGA', _('Recarga de Saldo')
        PAYMENT = 'PAGO', _('Pago de Clase')
        WITHDRAWAL = 'RETIRO', _('Retiro de Fondos')

    class TransactionStatus(models.TextChoices):
        PENDING = 'PENDIENTE', _('Pendiente')
        COMPLETED = 'COMPLETADO', _('Completado')
        FAILED = 'FALLIDO', _('Fallido')

    class PaymentMethod(models.TextChoices):
        YAPE = 'YAPE', 'Yape'
        PLIN = 'PLIN', 'Plin'
        CARD = 'TARJETA', 'Tarjeta Crédito/Débito'
        INTERNAL = 'SALDO', 'Saldo de Billetera'

    wallet = models.ForeignKey(
        Wallet, 
        on_delete=models.PROTECT, 
        related_name='transactions'
    )
    
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        help_text="Negative for outflows, positive for inflows"
    )
    
    transaction_type = models.CharField(
        max_length=20, 
        choices=TransactionType.choices
    )
    
    status = models.CharField(
        max_length=20, 
        choices=TransactionStatus.choices, 
        default=TransactionStatus.PENDING
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Audit fields
    destination_account = models.CharField(max_length=100, null=True, blank=True)
    payment_method = models.CharField(
        max_length=20, 
        choices=PaymentMethod.choices,
        null=True, blank=True
    )

    def __str__(self):
        return f"{self.transaction_type} - {self.amount}"

class PaymentDetail(models.Model):
    booking_id = models.BigIntegerField(
        unique=True, 
        help_text="ID from Booking MS (Reserva)"
    )
    
    transaction = models.OneToOneField(
        Transaction, 
        on_delete=models.CASCADE, 
        related_name='payment_detail'
    )
    
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    teacher_net_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return f"Payment for Booking #{self.booking_id}"