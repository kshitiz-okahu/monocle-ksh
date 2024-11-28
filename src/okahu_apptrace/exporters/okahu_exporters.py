from typing import Dict, Any
import os, warnings
from importlib import import_module
from opentelemetry.sdk.trace.export import SpanExporter, ConsoleSpanExporter
from okahu_apptrace.exporters.file_exporter import FileSpanExporter

okahu_exporters:Dict[str, Any] = {
    "s3": {"module": "okahu_apptrace.exporters.aws.s3_exporter", "class": "S3SpanExporter"},
    "blob": {"module":"okahu_apptrace.exporters.azure.blob_exporter", "class": "AzureBlobSpanExporter"},
    "okahu": {"module":"okahu_apptrace.exporters.okahu.okahu_exporter", "class": "OkahuSpanExporter"},
    "file": {"module":"okahu_apptrace.exporters.file_exporter", "class": "FileSpanExporter"}
}

def get_okahu_exporter() -> SpanExporter:
    exporter_name = os.environ.get("OKAHU_EXPORTER", "file")
    try:
        exporter_class_path  = okahu_exporters[exporter_name]
    except Exception as ex:
        warnings.warn(f"Unsupported Okahu span exporter setting {exporter_name}, using default FileSpanExporter.")
        return FileSpanExporter()
    try:
        exporter_module = import_module(exporter_class_path.get("module"))
        exporter_class = getattr(exporter_module, exporter_class_path.get("class"))
        return exporter_class()
    except Exception as ex:
        warnings.warn(f"Unable to set Okahu span exporter to {exporter_name}, error {ex}. Using ConsoleSpanExporter")
        return ConsoleSpanExporter()
