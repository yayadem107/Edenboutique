from django.urls import path

from .views import (
    CashierReportView,
    DashboardSummaryView,
    SalesReportView,
    StockReportView,
    TopArticlesReportView,
)

urlpatterns = [
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("reports/sales/", SalesReportView.as_view(), name="report-sales"),
    path("reports/top-articles/", TopArticlesReportView.as_view(), name="report-top-articles"),
    path("reports/stock/", StockReportView.as_view(), name="report-stock"),
    path("reports/cashiers/", CashierReportView.as_view(), name="report-cashiers"),
]
