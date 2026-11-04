from django import forms


def model_form(model, fields):
    return forms.modelform_factory(model, fields=fields)
