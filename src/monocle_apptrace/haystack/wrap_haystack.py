import inspect
from monocle_apptrace.utils import with_tracer_wrapper, get_fully_qualified_class_name, set_attribute, get_workflow_name

DATA_INPUT_KEY = "data.input"
WORKFLOW_TYPE_MAP = {
    "haystack": "workflow.haystack"
}

def get_embedding_model_for_vectorstore(instance):
    try:
        if hasattr(instance, 'get_component'):
            text_embedder = instance.get_component('text_embedder')
            if text_embedder and hasattr(text_embedder, 'model'):
                return text_embedder.model
    except:
        pass

    return None

framework_vector_store_mapping = {
    'haystack.components.retrievers.in_memory': lambda instance: {
        'provider': instance.__dict__.get("document_store").__class__.__name__,
        'embedding_model': get_embedding_model_for_vectorstore(instance),
        'type': 'vector_store',
    }
}

@with_tracer_wrapper
def task_wrapper(tracer, to_wrap, wrapped, instance, args, kwargs):
    if instance.__class__.__name__ in ("AgentExecutor"):
        return wrapped(*args, **kwargs)

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

def process_span(to_wrap, span, instance, args):
    span_index = 1
    if is_root_span(span):
        workflow_name = get_workflow_name(span)
        if workflow_name:
            span.set_attribute(f"entity.{span_index}.name", workflow_name)
        package_name = to_wrap.get('package')
        for (package, workflow_type) in WORKFLOW_TYPE_MAP.items():
            if (package_name is not None and package in package_name):
                span.set_attribute(f"entity.{span_index}.type", workflow_type)
        span_index += 1

def pre_task_processing(to_wrap, instance, args, span):
    try:
        if is_root_span(span):
            update_span_with_prompt_input(to_wrap=to_wrap, wrapped_args=args, span=span)
        update_span_with_context_input(to_wrap=to_wrap, wrapped_args=args, span=span)
    except:
        pass

def post_task_processing(to_wrap, span, return_value):
    try:
        update_span_with_context_output(to_wrap=to_wrap, return_value=return_value, span=span)
        if is_root_span(span):
            update_span_with_prompt_output(to_wrap, wrapped_args=return_value, span=span)
    except:
        pass

def is_root_span(curr_span):
    return curr_span.parent is None

def update_span_with_prompt_input(to_wrap, wrapped_args, span):
    input_arg_text = wrapped_args[0]
    if isinstance(input_arg_text, dict):
        span.add_event("data.input", input_arg_text)
    else:
        span.add_event("data.input", {"query": input_arg_text})

def update_span_with_context_input(to_wrap, wrapped_args, span):
    package_name = to_wrap.get('package')
    input_arg_text = ""
    if "haystack.components.retrievers.in_memory" in package_name:
        input_arg_text += get_attribute(DATA_INPUT_KEY)
    if input_arg_text:
        span.add_event(DATA_INPUT_KEY, {"question": input_arg_text})

def update_span_with_context_output(to_wrap, return_value, span):
    package_name = to_wrap.get('package')
    output_arg_text = ""
    if "haystack.components.retrievers.in_memory" in package_name:
        output_arg_text += " ".join([doc.content for doc in return_value['documents']])
        if len(output_arg_text) > 100:
            output_arg_text = output_arg_text[:100] + "..."
    if output_arg_text:
        span.add_event("data.output", {"response": output_arg_text})

def update_span_with_prompt_output(to_wrap, wrapped_args, span):
    package_name = to_wrap.get('package')
    if "haystack.core.pipeline.pipeline" in package_name:
        resp = get_nested_value(wrapped_args, ['llm', 'replies'])
        if resp is not None:
            span.add_event("data.output", {"response": resp})
    elif isinstance(wrapped_args, str):
        span.add_event("data.output", {"response": wrapped_args})
    elif isinstance(wrapped_args, dict):
        span.add_event("data.output", wrapped_args)
