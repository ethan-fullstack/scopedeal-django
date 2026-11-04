from apps.clients.models import Client, SoftwareRequest
from apps.common.forms import model_form

ClientForm = model_form(Client, ["name", "industry", "contact_email"])


RequestForm = model_form(SoftwareRequest, ["title", "description", "priority"])


DeveloperRequestForm = model_form(SoftwareRequest, ["client", "title", "description", "priority"])
