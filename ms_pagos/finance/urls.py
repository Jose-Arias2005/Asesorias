from django.urls import path
from .views import WalletCreateView, WalletDetailView, ChargeView, RechargeView

urlpatterns = [
    path('wallet/', WalletCreateView.as_view(), name='create_wallet'),
    path('wallet/<str:user_id>/', WalletDetailView.as_view(), name='get_wallet'),
    
    path('transaction/charge/', ChargeView.as_view(), name='charge'), 

    path('transaction/deposit/', RechargeView.as_view(), name='deposit'),
]