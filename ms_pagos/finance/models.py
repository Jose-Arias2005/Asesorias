from django.db import models

# Create your models here.
from django.utils.translation import gettext_lazy as _

class Wallet(models.Model):
    # El user_id sera un UUID
    user_id = models.CharField(
        max_length=50, 
        unique=True, 
        db_index=True, 
        verbose_name="User ID (ms users)"
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True) # Congelar fondos
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet {self.user_id} - S/ {self.balance}"

class Transaction(models.Model):
    class TransactionType(models.TextChoices):
        # Entrada de dinero
        RECHARGE = 'RECARGA', _('Recarga de Saldo')
        REFUND = 'REEMBOLSO', _('Reembolso')

        # Salidas de dinero
        FEE_CREATE_CLASS = 'COBRO_CREAR_CLASE', _('Comisión Creación Clase')
        PAYMENT_RESERVA = 'PAGO_RESERVA', _('Pago de Reserva')
        WITHDRAWAL = 'RETIRO', _('Retiro de Fondos')

    class TransactionStatus(models.TextChoices):
        PENDING = 'PENDIENTE', _('Pendiente')
        COMPLETED = 'COMPLETADO', _('Completado')
        FAILED = 'FALLIDO', _('Fallido')

    class PaymentMethod(models.TextChoices):
        YAPE = 'YAPE', _('Yape')
        PLIN = 'PLIN', _('Plin')
        CARD = 'TARJETA', _('Tarjeta Crédito/Débito')
        BALANCE = 'SALDO', _('Saldo Interno') # Cuando pagas con tu billetera
        BANK_TRANSFER = 'TRANSFERENCIA', _('Transferencia Bancaria')
        OTHER = 'OTRO', _('Otro')

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
        max_length=30, 
        choices=TransactionType.choices
    )
    
    status = models.CharField(
        max_length=20, 
        choices=TransactionStatus.choices, 
        default=TransactionStatus.PENDING
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.OTHER,
        help_text="Medio por el cual entró o salió el dinero"
    )

    # ========== ID que obtenemos del Orquestador ========== #
    # Microservicio del que viene
    reference_source = models.CharField(
        max_length=50, 
        null=True, 
        blank=True
    )

    # ID
    external_reference = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="ID externo (Reserva ID, Clase ID, etc)"
    )
    
    # JSONB en Postgres, diccionario que almacena informacion
    info = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Detalles extra (CCI, Banco, Errores, etc)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.amount}"