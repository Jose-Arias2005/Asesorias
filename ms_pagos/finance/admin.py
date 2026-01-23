from django.contrib import admin

# Register your models here.
from .models import Wallet, Transaction, PaymentDetail

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'balance', 'updated_at')
    # Por qué campos buscar (barra de búsqueda)
    search_fields = ('user_id',)
    # Hacer click en el ID para editar
    list_display_links = ('user_id',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'wallet', 'transaction_type', 'amount', 'status', 'created_at')
    # Filtros laterales (muy útiles)
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('wallet__user_id', 'id')
    
    readonly_fields = ('amount', 'transaction_type', 'wallet') 

@admin.register(PaymentDetail)
class PaymentDetailAdmin(admin.ModelAdmin):
    list_display = ('booking_id', 'transaction', 'teacher_net_amount')
    search_fields = ('booking_id',)