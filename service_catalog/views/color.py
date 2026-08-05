from service_catalog.models import ApprovalState
from service_catalog.models.instance import InstanceState
from service_catalog.models.request import RequestState

# State colors are used by both `text-*` and `text-bg-*`; keep every value
# legible in both light and dark contexts. Custom orange, graphite, purple,
# and teal utilities are defined in squest.css for distinct state mappings.
map_dict_request_state = {
    RequestState.ACCEPTED: "primary",
    RequestState.ON_HOLD: "warning",
    RequestState.SUBMITTED: "info",
    RequestState.REJECTED: "dark",
    RequestState.PROCESSING: "orange",
    RequestState.COMPLETE: "success",
    RequestState.FAILED: "danger",
    RequestState.CANCELED: "secondary",
    RequestState.ARCHIVED: "graphite"
}

map_dict_instance_state = {
    InstanceState.PENDING: "secondary",
    InstanceState.PROVISIONING: "primary",
    InstanceState.PROVISION_FAILED: "warning",
    InstanceState.AVAILABLE: "success",
    InstanceState.DELETE_FAILED: "danger",
    InstanceState.DELETING: "orange",
    InstanceState.UPDATING: "info",
    InstanceState.UPDATE_FAILED: "purple",
    InstanceState.DELETED: "dark",
    InstanceState.ARCHIVED: "graphite",
    InstanceState.ABORTED: "teal",
}

map_dict_step_state = {
    ApprovalState.APPROVED: "success",
    ApprovalState.REJECTED: "danger",
    ApprovalState.PENDING: "primary",
}

random_color = {
    "blue": "#0d6efd",
    "indigo": "#6610f2",
    "purple": "#6f42c1",
    "pink": "#d63384",
    "red": "#dc3545",
    "orange": "#fd7e14",
    "yellow": "#ffc107",
    "green": "#198754",
    "teal": "#20c997",
    "cyan": "#0dcaf0",
    "gray": "#6c757d",
    "primary": "#0d6efd",
    "secondary": "#6c757d",
    "success": "#198754",
    "info": "#0dcaf0",
    "warning": "#ffc107",
    "danger": "#dc3545",
    "light": "#f8f9fa"
}
