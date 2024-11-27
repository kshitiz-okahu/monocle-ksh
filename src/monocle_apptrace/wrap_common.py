# pylint: disable=protected-access
import logging
import os
from urllib.parse import urlparse
from opentelemetry.trace import Span, Tracer
from monocle_apptrace.utils import resolve_from_alias, update_span_with_infra_name, with_tracer_wrapper, get_embedding_model, get_attribute, get_workflow_name, set_embedding_model
from monocle_apptrace.utils import set_attribute
from monocle_apptrace.utils import get_fully_qualified_class_name, flatten_dict, get_nested_value
from opentelemetry.context import get_value, attach, set_value

logger = logging.getLogger(__name__)
WORKFLOW_TYPE_KEY = "workflow_type"
DATA_INPUT_KEY = "data.input"
DATA_OUTPUT_KEY = "data.output"
PROMPT_INPUT_KEY = "data.input"
PROMPT_OUTPUT_KEY = "data.output"
QUERY = "question"
RESPONSE = "response"
SESSION_PROPERTIES_KEY = "session"
INFRA_SERVICE_KEY = "infra_service_name"

TYPE = "type"
PROVIDER = "provider_name"
EMBEDDING_MODEL = "embedding_model"
VECTOR_STORE = 'vector_store'
META_DATA = 'metadata'

@with_tracer_wrapper
def task_wrapper(tracer: Tracer, to_wrap, wrapped, instance, args, kwargs):
    """Instruments and calls every function defined in TO_WRAP."""

    if hasattr(instance, "name") and instance.name:
        name = f"{to_wrap.get('span_name')}.{instance.name.lower()}"
    elif to_wrap.get("span_name"):
        name = to_wrap.get("span_name")
    else:
        name = get_fully_qualified_class_name(instance)

    with tracer.start_as_current_span(name) as span:
        process_span(to_wrap, span, instance, args)
        pre_task_processing(to_wrap, instance, args, span)
        return_value = wrapped(*args, **kwargs)
        post_task_processing(to_wrap, span, return_value)

    return return_value

def get_workflow_input(args, inputs):
    if args is not None and len(args) > 0:
        for value in args[0].values():
            for text in value.values():
                inputs.add(text)

    workflow_input: str = ""

    if inputs is not None and len(inputs) > 0:
        for input_str in inputs:
            workflow_input = workflow_input + input_str
    return workflow_input

def process_span(to_wrap, span, instance, args):
    span_index = 1
    if is_root_span(span):
        workflow_name = get_workflow_name(span)
        if workflow_name:
            span.set_attribute(f"entity.{span_index}.name", workflow_name)
        package_name = to_wrap.get('package')
        span_index += 1
    if 'output_processor' in to_wrap:
        output_processor=to_wrap['output_processor']
        if isinstance(output_processor, dict) and len(output_processor) > 0:
            if 'type' in output_processor:
                span.set_attribute("span.type", output_processor['type'])
            else:
                logger.warning("type of span not found or incorrect written in entity json")
            count = 0
            if 'attributes' in output_processor:
                count = len(output_processor["attributes"])
                span.set_attribute("entity.count", count)
                span_index = 1
                for processors in output_processor["attributes"]:
                    for processor in processors:
                        attribute = processor.get('attribute')
                        accessor = processor.get('accessor')

                        if attribute and accessor:
                            attribute_name = f"entity.{span_index}.{attribute}"
                            try:
                                result = eval(accessor)(instance, args)
                                if result and isinstance(result, str):
                                    span.set_attribute(attribute_name, result)
                            except Exception as e:
                                logger.error(f"Error processing accessor: {e}")
                        else:
                            logger.warning(f"{' and '.join([key for key in ['attribute', 'accessor'] if not processor.get(key)])} not found or incorrect in entity JSON")
                    span_index += 1
            else:
                logger.warning("attributes not found or incorrect written in entity json")
                span.set_attribute("span.count", count)

        else:
            logger.warning("empty or entities json is not in correct format")

def post_task_processing(to_wrap, span, return_value):
    try:
        update_span_with_context_output(to_wrap=to_wrap, return_value=return_value, span=span)

        if is_root_span(span):
            update_span_with_prompt_output(to_wrap=to_wrap, wrapped_args=return_value, span=span)
    except:
        logger.exception("exception in post_task_processing")

def pre_task_processing(to_wrap, instance, args, span):
    try:
        if is_root_span(span):
            update_span_with_prompt_input(to_wrap=to_wrap, wrapped_args=args, span=span)
            update_span_with_infra_name(span, INFRA_SERVICE_KEY)

        update_span_with_context_input(to_wrap=to_wrap, wrapped_args=args, span=span)
    except:
        logger.exception("exception in pre_task_processing")

@with_tracer_wrapper
async def atask_wrapper(tracer, to_wrap, wrapped, instance, args, kwargs):
    if hasattr(instance, "name") and instance.name:
        name = f"{to_wrap.get('span_name')}.{instance.name.lower()}"
    elif to_wrap.get("span_name"):
        name = to_wrap.get("span_name")
    else:
        name = get_fully_qualified_class_name(instance)

    with tracer.start_as_current_span(name) as span:
        process_span(to_wrap, span, instance, args)
        pre_task_processing(to_wrap, instance, args, span)
        return_value = await wrapped(*args, **kwargs)
        post_task_processing(to_wrap, span, return_value)

    return return_value

@with_tracer_wrapper
async def allm_wrapper(tracer, to_wrap, wrapped, instance, args, kwargs):
    if callable(to_wrap.get("span_name_getter")):
        name = to_wrap.get("span_name_getter")(instance)

    elif hasattr(instance, "name") and instance.name:
        name = f"{to_wrap.get('span_name')}.{instance.name.lower()}"
    elif to_wrap.get("span_name"):
        name = to_wrap.get("span_name")
    else:
        name =  get_fully_qualified_class_name(instance)
    with tracer.start_as_current_span(name) as span:
        provider_name, inference_endpoint = get_provider_name(instance)
        instance_args = {"provider_name": provider_name, "inference_endpoint": inference_endpoint}
        process_span(to_wrap, span, instance, instance_args)
        return_value = await wrapped(*args, **kwargs)
        update_span_from_llm_response(response=return_value, span=span, instance=instance)

    return return_value

@with_tracer_wrapper
def llm_wrapper(tracer: Tracer, to_wrap, wrapped, instance, args, kwargs):
    if callable(to_wrap.get("span_name_getter")):
        name = to_wrap.get("span_name_getter")(instance)

    elif hasattr(instance, "name") and instance.name:
        name = f"{to_wrap.get('span_name')}.{instance.name.lower()}"
    elif to_wrap.get("span_name"):
        name = to_wrap.get("span_name")
    else:
        name =  get_fully_qualified_class_name(instance)

    with tracer.start_as_current_span(name) as span:
        provider_name, inference_endpoint = get_provider_name(instance)
        instance_args = {"provider_name": provider_name, "inference_endpoint": inference_endpoint}
        process_span(to_wrap, span, instance, instance_args)
        return_value = wrapped(*args, **kwargs)
        update_span_from_llm_response(response=return_value, span=span, instance=instance)

    return return_value

def update_llm_endpoint(curr_span: Span, instance):
    __set_span_attribute_if_not_none = lambda span, **kwargs: [
        span.set_attribute(k, v) for k, v in kwargs.items() if v is not None
    ]

    triton_llm_endpoint = os.environ.get("TRITON_LLM_ENDPOINT")
    if triton_llm_endpoint is not None and len(triton_llm_endpoint) > 0:
        curr_span.set_attribute("server_url", triton_llm_endpoint)
    else:
        temp_val = instance.__dict__.get("temperature")
        model_name = resolve_from_alias(instance.__dict__, ["model", "model_name"])
        deployment_name = resolve_from_alias(instance.__dict__,
                                             ["engine", "azure_deployment", "deployment_name", "deployment_id",
                                              "deployment"])
        inference_ep = resolve_from_alias(instance.__dict__, ["azure_endpoint", "api_base"])

        __set_span_attribute_if_not_none(
            curr_span,
            temperature=temp_val,
            model_name=model_name,
            az_openai_deployment=deployment_name,
            inference_endpoint=inference_ep
        )

def get_provider_name(instance):
    provider_url = ""
    inference_endpoint = ""
    try:
        if isinstance(instance.client._client.base_url.host, str):
            provider_url = instance.client._client.base_url.host
        if isinstance(instance.client._client.base_url, str):
            inference_endpoint = instance.client._client.base_url
        else:
            inference_endpoint = str(instance.client._client.base_url)
    except:
        pass

    try:
        if isinstance(instance.api_base, str):
            provider_url = instance.api_base
    except:
        pass

    try:
        if len(provider_url) > 0:
            parsed_provider_url = urlparse(provider_url)
    except:
        pass
    return parsed_provider_url.hostname or provider_url,inference_endpoint

def is_root_span(curr_span: Span) -> bool:
    return curr_span.parent is None

def get_input_from_args(chain_args):
    if len(chain_args) > 0 and isinstance(chain_args[0], str):
        return chain_args[0]
    return ""

def update_span_from_llm_response(response, span: Span, instance):
    if (response is not None and isinstance(response, dict) and "meta" in response) or (response is not None and hasattr(response, "response_metadata")):
        token_usage = None
        if (response is not None and isinstance(response, dict) and "meta" in response):
            token_usage = response["meta"][0]["usage"]

        if (response is not None and hasattr(response, "response_metadata")):
            response_metadata = response.response_metadata
            token_usage = response_metadata.get("token_usage")

        meta_dict = {}
        if token_usage is not None:
            temperature = instance.__dict__.get("temperature", None)
            meta_dict.update({"temperature": temperature})
            meta_dict.update({"completion_tokens": token_usage.get("completion_tokens")})
            meta_dict.update({"prompt_tokens": token_usage.get("prompt_tokens")})
            meta_dict.update({"total_tokens": token_usage.get("total_tokens")})
            span.add_event(META_DATA, meta_dict)
    if (response is not None and hasattr(response, "raw")):
        try:
            meta_dict = {}
            if response.raw is not None:
                token_usage = response.raw.get("usage") if isinstance(response.raw, dict) else getattr(response.raw,
                                                                                                       "usage", None)
                if token_usage is not None:
                    temperature = instance.__dict__.get("temperature", None)
                    meta_dict.update({"temperature": temperature})
                    if getattr(token_usage, "completion_tokens", None):
                        meta_dict.update({"completion_tokens": getattr(token_usage, "completion_tokens")})
                    if getattr(token_usage, "prompt_tokens", None):
                        meta_dict.update({"prompt_tokens": getattr(token_usage, "prompt_tokens")})
                    if getattr(token_usage, "total_tokens", None):
                        meta_dict.update({"total_tokens": getattr(token_usage, "total_tokens")})
                    span.add_event(META_DATA, meta_dict)
        except AttributeError:
            token_usage = None

def update_workflow_type(to_wrap, span: Span):
    package_name = to_wrap.get('package')

def update_span_with_context_input(to_wrap, wrapped_args, span: Span):
    input_arg_text = ""

    if input_arg_text:
        span.add_event(DATA_INPUT_KEY, {QUERY: input_arg_text})

def update_span_with_context_output(to_wrap, return_value, span: Span):
    output_arg_text = ""

    if output_arg_text:
        span.add_event(DATA_OUTPUT_KEY, {RESPONSE: output_arg_text})

def update_span_with_prompt_input(to_wrap, wrapped_args, span: Span):
    input_arg_text = wrapped_args[0]

    prompt_inputs = get_nested_value(input_arg_text, ['prompt_builder'])
    if prompt_inputs is not None:
        input_arg_text = flatten_dict(prompt_inputs)
        span.add_event(PROMPT_INPUT_KEY, input_arg_text)
    elif isinstance(input_arg_text, dict):
        span.add_event(PROMPT_INPUT_KEY, input_arg_text)
    else:
        span.add_event(PROMPT_INPUT_KEY, {QUERY: input_arg_text})

def update_span_with_prompt_output(to_wrap, wrapped_args, span: Span):
    if isinstance(wrapped_args, str):
        span.add_event(PROMPT_OUTPUT_KEY, {RESPONSE: wrapped_args})
    elif isinstance(wrapped_args, dict):
        span.add_event(PROMPT_OUTPUT_KEY,  wrapped_args)
