from django.contrib import admin

# Register your models here.
from .models import Wallet, Transaction

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'balance', 'is_active', 'updated_at')
    search_fields = ('user_id',)
    list_filter = ('is_active', 'updated_at')
    
    # Opcional: Para que no puedan cambiar el user_id una vez creado
    readonly_fields = ('updated_at',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    # Mostramos las columnas clave de la nueva arquitectura
    list_display = (
        'id', 
        'wallet', 
        'transaction_type', 
        'amount', 
        'status', 
        'payment_method',
        'external_reference', # Importante para ver el ID de la reserva/clase
        'created_at'
    )
    
    # Filtros laterales potentes
    list_filter = (
        'transaction_type', 
        'status', 
        'payment_method', 
        'created_at',
        'reference_source'
    )
    
    # Buscador: Ahora busca por ID de usuario O por referencia externa (ID Reserva)
    search_fields = ('wallet__user_id', 'id', 'external_reference')
    
    # Campos de solo lectura para evitar fraudes manuales por error
    readonly_fields = ('created_at',)
    
    # Organizar el formulario de edición por secciones
    fieldsets = (
        ('Detalle Financiero', {
            'fields': ('wallet', 'amount', 'transaction_type', 'payment_method', 'status')
        }),
        ('Referencias Externas', {
            'fields': ('external_reference', 'reference_source', 'description')
        }),
        ('Metadata Técnica', {
            'fields': ('info', 'created_at') # Aquí verás el JSON bonito
        }),
    )