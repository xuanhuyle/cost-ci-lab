{% macro net_revenue(price, discount) -%}
    ({{ price }} * (1 - {{ discount }}))
{%- endmacro %}
