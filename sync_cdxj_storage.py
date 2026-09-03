import argparse
import os
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig


ROOT = Path(__file__).resolve().parent
MULTIPART = TransferConfig(
    multipart_threshold=64 * 1024 * 1024,
    multipart_chunksize=32 * 1024 * 1024,
    max_concurrency=8,
    use_threads=True,
)


def storage_client():
    endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip()
    access_key = os.environ.get("S3_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("S3_SECRET_ACCESS_KEY", "").strip()
    if not endpoint or not access_key or not secret_key:
        raise RuntimeError("S3_ENDPOINT_URL, S3_ACCESS_KEY_ID e S3_SECRET_ACCESS_KEY sao obrigatorios")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.environ.get("S3_REGION", "auto"),
    )


def bucket_name():
    value = os.environ.get("S3_BUCKET", "").strip()
    if not value:
        raise RuntimeError("S3_BUCKET e obrigatorio")
    return value


def object_prefix():
    value = os.environ.get("S3_PREFIX", "noticias-de-ontem").strip().strip("/")
    return f"{value}/" if value else ""


def local_files(workspace, include_index_state=False):
    cdxj_dir = workspace / "arquivo_cdxj"
    if cdxj_dir.exists():
        for path in sorted(cdxj_dir.glob("*/*.cdxj")):
            yield path, path.relative_to(workspace).as_posix()
    state_names = ["arquivo_cdxj_state.json"]
    if include_index_state:
        state_names.append("topic_index_state.json")
    for name in state_names:
        path = workspace / name
        if path.exists():
            yield path, name


def remote_objects(client, bucket, prefix):
    objects = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            objects[item["Key"]] = item
    return objects


def remote_metadata(client, bucket, key):
    try:
        return client.head_object(Bucket=bucket, Key=key).get("Metadata", {})
    except Exception:
        return {}


def upload(workspace, include_index_state=False):
    client = storage_client()
    bucket = bucket_name()
    prefix = object_prefix()
    remote = remote_objects(client, bucket, prefix)
    uploaded = 0
    skipped = 0
    for path, relative in local_files(workspace, include_index_state):
        key = prefix + relative
        stat = path.stat()
        item = remote.get(key)
        metadata = remote_metadata(client, bucket, key) if item and item.get("Size") == stat.st_size else {}
        if item and item.get("Size") == stat.st_size and metadata.get("mtime_ns") == str(stat.st_mtime_ns):
            skipped += 1
            continue
        client.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs={"Metadata": {"mtime_ns": str(stat.st_mtime_ns)}},
            Config=MULTIPART,
        )
        uploaded += 1
        print(f"[storage] enviado: {relative}", flush=True)
    print(f"[storage] upload concluido: {uploaded} enviados, {skipped} sem alteracoes.")


def safe_target(workspace, relative):
    target = (workspace / relative).resolve()
    workspace_resolved = workspace.resolve()
    if target != workspace_resolved and workspace_resolved not in target.parents:
        raise RuntimeError(f"Caminho remoto inseguro: {relative}")
    return target


def download(workspace, include_index_state=False):
    client = storage_client()
    bucket = bucket_name()
    prefix = object_prefix()
    remote = remote_objects(client, bucket, prefix)
    downloaded = 0
    skipped = 0
    allowed_files = {"arquivo_cdxj_state.json"}
    if include_index_state:
        allowed_files.add("topic_index_state.json")
    for key, item in sorted(remote.items()):
        relative = key[len(prefix):]
        if not (relative.startswith("arquivo_cdxj/") and relative.endswith(".cdxj")) and relative not in allowed_files:
            continue
        target = safe_target(workspace, relative)
        metadata = remote_metadata(client, bucket, key)
        mtime_ns = int(metadata.get("mtime_ns") or 0)
        if target.exists() and target.stat().st_size == item.get("Size") and (not mtime_ns or target.stat().st_mtime_ns == mtime_ns):
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".part")
        client.download_file(bucket, key, str(temporary), Config=MULTIPART)
        temporary.replace(target)
        if mtime_ns:
            os.utime(target, ns=(mtime_ns, mtime_ns))
        downloaded += 1
        print(f"[storage] recebido: {relative}", flush=True)
    print(f"[storage] download concluido: {downloaded} recebidos, {skipped} sem alteracoes.")


def main():
    parser = argparse.ArgumentParser(description="Sincroniza CDXJ e estados com armazenamento S3/R2 privado.")
    parser.add_argument("direction", choices=["upload", "download"])
    parser.add_argument("--workspace", default=str(ROOT))
    parser.add_argument("--include-index-state", action="store_true")
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if args.direction == "upload":
        upload(workspace, args.include_index_state)
    else:
        download(workspace, args.include_index_state)


if __name__ == "__main__":
    main()
