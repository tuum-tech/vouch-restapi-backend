import falcon
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from app import log, config, redisBroker, seedDatabase
from app.middleware import AuthMiddleware
from app.api.common import base
from app.api.v1 import providers, validationtx, services
from app.cronjob import resend_validations_without_response
from app.model import provider
from app.errors import AppError
from mongoengine import connect

LOG = log.get_logger()


class App(falcon.API):
    def __init__(self, *args, **kwargs):
        super(App, self).__init__(*args, **kwargs)
        LOG.info("API Server is starting")

        # Simple endpoint for base
        self.add_route("/", base.BaseResource())

        # Register a provider manually
        self.add_route("/v1/providers/create", providers.CreateProvider())
        # Retrieves all providers
        self.add_route("/v1/providers", providers.ProvidersCollection())
        # Retrieves providers from validation type
        self.add_route("/v1/providers/validationType/{validation_type}",
                       providers.ProvidersFromValidationTypeCollection())

        # Retrieves all services by provider did
        self.add_route("/v1/services/provider_did/{provider_did}", services.ServicesFromProviderDid())

        # Creates a new transaction
        self.add_route("/v1/validationtx/create", validationtx.CreateValidationTx())
        # Retrieves all transactions according to did
        self.add_route("/v1/validationtx/did/{did}", validationtx.ValidationTxFromDid())
        # Retrieves all transactions according to provider id
        self.add_route("/v1/validationtx/provider_id/{provider_id}", validationtx.ValidationTxFromProviderId())
        # Retrieves all transactions according to provider did
        self.add_route("/v1/validationtx/provider_did/{provider_did}", validationtx.ValidationTxFromProviderDid())
        # Retrieves transaction according to confirmation ID
        self.add_route("/v1/validationtx/confirmation_id/{confirmation_id}", validationtx.ValidationTxFromConfirmationId())
        # Retrieves transaction count according to provider ID
        self.add_route("/v1/validationtx/count/provider_id/{provider_id}", validationtx.ValidationTxCountFromProviderId())
        # Update isSavedOnProfile information
        self.add_route("/v1/validationtx/is_saved/confirmation_id/{confirmation_id}", validationtx.SetIsSavedValidationTx())
        # Approve validation by manual validator
        self.add_route("/v1/validationtx/approve/confirmation_id/{confirmation_id}", validationtx.ApproveValidationTx())
        # Reject validation by manual validator
        self.add_route("/v1/validationtx/reject/confirmation_id/{confirmation_id}", validationtx.RejectValidationTx())
        # Cancel validation
        self.add_route("/v1/validationtx/cancel/confirmation_id/{confirmation_id}", validationtx.CancelValidationTx())

        self.add_error_handler(AppError, AppError.handle)


# Connect to mongodb
LOG.info("Connecting to mongodb...")
if config.PRODUCTION:
    connect(
        config.MONGO['DATABASE'],
        host="mongodb+srv://" + config.MONGO['USERNAME'] + ":" + config.MONGO['PASSWORD'] + "@" +
             config.MONGO['HOST'] + "/?retryWrites=true&w=majority"
    )
else:
    connect(
        config.MONGO['DATABASE'],
        host="mongodb://" + config.MONGO['USERNAME'] + ":" + config.MONGO['PASSWORD'] + "@" +
             config.MONGO['HOST'] + ":" + str(config.MONGO['PORT']) + "/?authSource=admin"
    )

LOG.info("Initializing the Falcon REST API service...")
application = App(middleware=[
    AuthMiddleware(),
])

seedDatabase.seed_database()

# Temporary status update
seedDatabase.update_pending_validation_status()

th = threading.Thread(target=redisBroker.monitor_redis)
th.setDaemon(True)
th.start()

scheduler = BackgroundScheduler()
scheduler.add_job(resend_validations_without_response, 'interval', seconds=config.CRON_INTERVAL)
scheduler.start()
