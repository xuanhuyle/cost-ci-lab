{% macro net_revenue(price, discount) -%}
    round({{ price }} * (1 - coalesce({{ discount }}, 0)), 2)
{%- endmacro %}
