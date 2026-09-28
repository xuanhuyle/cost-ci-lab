{% macro run_date() -%}
    cast('{{ var("run_date") }}' as date)
{%- endmacro %}

{# dbt.dateadd returns a TIMESTAMP on some adapters (e.g. dbt-duckdb); comparing a DATE column
   with a TIMESTAMP casts the column and silently disables zone-map/partition pruning.
   Cast back to DATE so date filters stay prunable. #}
{% macro run_date_minus(amount, datepart='day') -%}
    cast({{ dbt.dateadd(datepart, -amount, run_date()) }} as date)
{%- endmacro %}
