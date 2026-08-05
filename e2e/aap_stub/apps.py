import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AapStubConfig(AppConfig):
    """Closes the RHAAP/AWX boundary onto the in-process stub for the end to end suite.

    Installed only by ``e2e.settings_e2e``, so importing Squest with its normal settings is
    unaffected.
    """

    name = "e2e.aap_stub"
    label = "aap_stub"

    def ready(self):
        from service_catalog.forms import tower_server_forms
        from service_catalog.models.tower_server import TowerServer

        from .fake_tower import FakeTower

        def get_tower_instance(self):
            return FakeTower(self.host, None, None, secure=self.secure, ssl_verify=self.ssl_verify, token=self.token,
                             aap_environment=self.aap_environment)

        TowerServer.get_tower_instance = get_tower_instance
        # the form validates credentials by building a Tower itself instead of going through the model
        tower_server_forms.Tower = FakeTower
        logger.warning("[aap-stub] RHAAP/AWX calls are stubbed in process")
