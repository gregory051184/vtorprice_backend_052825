from django.dispatch import Signal

recyclables_deal_status_changed = Signal()
equipment_deal_status_changed = Signal()

application_status_changed = Signal()

deal_completed = Signal()
