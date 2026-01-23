from django.urls import path
from .views import WalletView, RechargeView, PaymentView

urlpatterns = [
    # api/wallet/20231001/
    path('wallet/<str:user_id>/', WalletView.as_view(), name='get_wallet'),
    # api/wallet/create/
    path('wallet/', WalletView.as_view(), name='create_wallet'),

    path('recharge/', RechargeView.as_view(), name='recharge'),
    path('pay/', PaymentView.as_view(), name='pay'),
]