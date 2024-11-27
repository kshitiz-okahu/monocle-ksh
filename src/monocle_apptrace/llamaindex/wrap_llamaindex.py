import inspect
from monocle_apptrace.utils import with_tracer_wrapper, get_fully_qualified_class_name, set_attribute, get_workflow_name

DATA_INPUT_KEY = "data.input"
WORKFLOW_TYPE_MAP = {
    "llamaindex": "workflow.llamaindex"
}

def get_embedding_model_for_vectorstore(instance):
    if hasattr(instance, '_embed_model') and hasattr(instance._embed_model, 'model_name'):
        return instance._embed_model.model_name
    return "Unknown Embedding Model"

framework_vector_store_mapping = {
    'llama_index.core.indices.base_retriever': lambda instance: {
        'provider': type(instance._vector_store).__name__,
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
    if "llama_index.core.indices.base_retriever" in package_name and len(wrapped_args) > 0:
        input_arg_text += wrapped_args[0].query_str
    if input_arg_text:
        span.add_event(DATA_INPUT_KEY, {"question": input_arg_text})

def update_span_with_context_output(to_wrap, return_value, span):
    package_name = to_wrap.get('package')
    output_arg_text = ""
    if "llama_index.core.indices.base_retriever" in package_name and len(return_value) > 0:
        output_arg_text += return_value[0].text
    if output_arg_text:
        span.add_event("data.output", {"response": output_arg_text})

def update_span_with_prompt_output(to_wrap, wrapped_args, span):
    package_name = to_wrap.get('package')
    if "llama_index.core.base.base_query_engine" in package_name:
        span.add_event("data.output", {"response": wrapped_args.response})
    elif isinstance(wrapped_args, str):
        span.add_event("data.output", {"response": wrapped_args})
    elif isinstance(wrapped_args, dict):
        span.add_event("data.output", wrapped_args)
