# Guia dos CDXJ: extração, validação e cópia

Este guia começa no estado atual do projeto português **Notícias de Ontem**.

A extração dos CDXJ ainda está em curso. Não configures alojamento dinâmico,
OpenSearch, Render, R2, PostgreSQL ou workers nesta fase.

O percurso a seguir é apenas:

1. terminar a extração;
2. confirmar que todas as coleções do Arquivo.pt foram processadas;
3. reconstruir a cobertura uma única vez;
4. validar os ficheiros resultantes;
5. criar uma cópia privada gratuita;
6. gerar e publicar o site estático.

## Regra principal

Enquanto `build_arquivo_cdxj_index.py` estiver ativo:

- não inicies outra extração;
- não executes `reconstruir_cobertura_cdxj.cmd`;
- não sincronizes `arquivo_cdxj/` para armazenamento remoto;
- não construas o índice de texto;
- não apagues checkpoints de `arquivo_cdxj_state.json`.

A pequena reconstrução efetuada há algumas semanas foi apenas intermédia. A
cobertura terá de ser reconstruída novamente depois de a extração completa
terminar.

## 1. Deixar terminar a extração atual

Confirma se o processo continua ativo:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'build_arquivo_cdxj_index\.py' } |
  Select-Object ProcessId, CreationDate, CommandLine
```

Se aparecer um processo com `--all-remote`, deixa-o continuar.

O progresso fica em `arquivo_cdxj_state.json`. Para ver a coleção que está
realmente a ser transferida:

```powershell
$state = Get-Content arquivo_cdxj_state.json -Raw | ConvertFrom-Json

$state.in_progress.PSObject.Properties.Value |
  Where-Object { $_.bytes_downloaded -gt 0 } |
  Select-Object name, updated_at, bytes_downloaded, scanned, written
```

Algumas entradas em `in_progress` podem ter zero bytes por causa de tentativas
anteriores. Isso não significa que estejam todas a ser transferidas ao mesmo
tempo.

## 2. Retomar se o processo parar

Se já não existir um processo ativo e a extração não estiver completa:

```cmd
recolher_cdxj_arquivo_pt.cmd 1996 2026
```

O comando volta a consultar o manifesto, ignora coleções concluídas e
inalteradas e retoma checkpoints compatíveis.

Não escolhas as coleções em falta com base na numeração. Há coleções com
números superiores já concluídas e o Arquivo.pt pode acrescentar coleções novas
entre duas execuções.

## 3. Comparar o estado com o Arquivo.pt

Depois de o processo terminar, calcula a diferença entre o manifesto remoto e
as coleções concluídas:

```powershell
$html = (Invoke-WebRequest `
  -UseBasicParsing `
  'https://arquivo.pt/datasets/cdxj/' `
  -TimeoutSec 60).Content

$remote = [regex]::Matches(
  $html,
  'href="([^"]+\.cdxj(?:_filtered)?)"'
) | ForEach-Object {
  $_.Groups[1].Value
} | Sort-Object -Unique

$state = Get-Content arquivo_cdxj_state.json -Raw | ConvertFrom-Json
$processed = @($state.processed.PSObject.Properties.Value.name)
$missing = @($remote | Where-Object { $_ -notin $processed })

[pscustomobject]@{
  Publicadas = $remote.Count
  Concluidas = $processed.Count
  EmFalta = $missing.Count
}

$missing
```

O resultado pretendido é:

```text
EmFalta = 0
```

Se aparecerem coleções em falta, volta a executar:

```cmd
recolher_cdxj_arquivo_pt.cmd 1996 2026
```

Repete a comparação quando terminar. Uma nova execução é necessária porque o
manifesto pode ter mudado enquanto a execução anterior estava em curso.

## 4. Verificar falhas e checkpoints

Quando `EmFalta` for zero, verifica o estado:

```powershell
$state = Get-Content arquivo_cdxj_state.json -Raw | ConvertFrom-Json

[pscustomobject]@{
  Processadas = @($state.processed.PSObject.Properties).Count
  EmProgresso = @($state.in_progress.PSObject.Properties).Count
  Falhadas = @($state.failed.PSObject.Properties).Count
}

$state.failed.PSObject.Properties.Value |
  Select-Object name, failed_at, reason, error
```

O objetivo é não ter coleções publicadas por processar. Entradas antigas em
`failed` ou `in_progress` devem desaparecer quando a respetiva coleção terminar
com sucesso.

Não edites manualmente o JSON para esconder falhas.

## 5. Reconstruir a cobertura final

Executa este passo apenas quando:

- não houver processo de extração ativo;
- `EmFalta` for zero;
- não existirem transferências parciais relevantes.

Então executa:

```cmd
reconstruir_cobertura_cdxj.cmd
```

Este comando relê os CDXJ filtrados, atualiza a cobertura por fonte e gera
novamente o site.

Confirma que `arquivo_cdxj_state.json` contém:

- `domain_coverage`;
- `coverage_updated_at`;
- datas mínimas e máximas coerentes com os ficheiros existentes.

## 6. Validar os ficheiros locais

Conta os ficheiros e mede o volume:

```powershell
$files = Get-ChildItem .\arquivo_cdxj -Recurse -File -Filter *.cdxj

[pscustomobject]@{
  Ficheiros = $files.Count
  Bytes = ($files | Measure-Object Length -Sum).Sum
  GiB = [math]::Round(
    ($files | Measure-Object Length -Sum).Sum / 1GB,
    2
  )
}
```

Confirma também que o Git não está a tentar incluir os CDXJ:

```powershell
git status --short
```

Nunca devem entrar no Git:

- `arquivo_cdxj/`;
- CDXJ brutos;
- bases de dados e caches grandes;
- arquivos comprimidos dos CDXJ;
- dados de índices de pesquisa.

## 7. Criar a cópia privada gratuita

Só depois da validação local, cria um **Hugging Face Storage Bucket privado**.

Esta é a solução escolhida porque a conta gratuita inclui atualmente 100 GB de
armazenamento privado e o conjunto local está ainda bastante abaixo desse
valor. Confirma o limite apresentado na conta antes do primeiro envio:

- [limites de armazenamento](https://huggingface.co/docs/hub/storage-limits);
- [documentação dos Storage Buckets](https://huggingface.co/docs/hub/storage-buckets).

Instala a ferramenta e autentica:

```powershell
python -m pip install --upgrade huggingface_hub
hf auth login
```

Cria o bucket. Substitui `<namespace>` pelo teu utilizador ou organização:

```powershell
hf buckets create <namespace>/noticias-de-ontem-cdxj --private
```

Pré-visualiza o primeiro envio:

```powershell
hf buckets sync `
  .\arquivo_cdxj `
  hf://buckets/<namespace>/noticias-de-ontem-cdxj/arquivo_cdxj `
  --dry-run
```

Executa o envio:

```powershell
hf buckets sync `
  .\arquivo_cdxj `
  hf://buckets/<namespace>/noticias-de-ontem-cdxj/arquivo_cdxj
```

Envia o estado:

```powershell
hf buckets cp `
  .\arquivo_cdxj_state.json `
  hf://buckets/<namespace>/noticias-de-ontem-cdxj/arquivo_cdxj_state.json
```

Não uses `--delete`. Não é necessário para o primeiro envio e pode apagar
objetos remotos.

Não uses `sync_cdxj_storage.py` com este bucket. Esse script depende de
metadados S3 personalizados que o gateway do Hugging Face não conserva. Para
este armazenamento, usa sempre `hf buckets sync`.

## 8. Verificar a cópia

Lista o conteúdo remoto:

```powershell
hf buckets list <namespace>/noticias-de-ontem-cdxj --tree -h -R
```

Repete a simulação:

```powershell
hf buckets sync `
  .\arquivo_cdxj `
  hf://buckets/<namespace>/noticias-de-ontem-cdxj/arquivo_cdxj `
  --dry-run
```

Se os ficheiros locais não tiverem mudado desde o envio, não devem aparecer
novas transferências inesperadas.

## 9. Gerar e publicar o site

Depois de a cobertura final e a cópia remota estarem validadas:

```cmd
python -u build_site.py
```

Publica apenas `site/` através do workflow existente do GitHub Pages.

O site não deve descarregar os CDXJ durante a publicação nem em tempo de
execução. O bucket é apenas uma cópia de construção e restauro.

## Atualizações posteriores

Quando o Arquivo.pt publicar coleções novas:

```cmd
recolher_cdxj_arquivo_pt.cmd 1996 2026
reconstruir_cobertura_cdxj.cmd
```

Depois sincroniza apenas as alterações:

```powershell
hf buckets sync `
  .\arquivo_cdxj `
  hf://buckets/<namespace>/noticias-de-ontem-cdxj/arquivo_cdxj

hf buckets cp `
  .\arquivo_cdxj_state.json `
  hf://buckets/<namespace>/noticias-de-ontem-cdxj/arquivo_cdxj_state.json
```

Não é necessário executar esta rotina diariamente. Uma verificação semanal ou
após o anúncio de novas coleções é suficiente.

## Ponto de paragem

Não avances para alojamento dinâmico ou para um índice integral enquanto estes
passos não estiverem concluídos:

- extração terminada;
- diferença para o manifesto igual a zero;
- falhas revistas;
- cobertura final reconstruída;
- ficheiros locais validados;
- cópia privada confirmada;
- site estático gerado e publicado.
