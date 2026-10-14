#!/bin/bash
# E2E part 2: inside real WordPress/WooCommerce, using the plugin's own code.
cd /home/claude/wp
TOK=$(python3 -c "import json;print(json.load(open('state.json'))['adapter_token'])"); CPID=$(python3 -c "import json;print(json.load(open('state.json'))['product_id'])")
W="php wp-cli.phar --allow-root --path=wordpress"
$W eval "\$cr=new AIOL_Credentials(); \$r=\$cr->save('http://127.0.0.1:8000', '$TOK'); echo is_wp_error(\$r)?'save error: '.\$r->get_error_message():'credentials saved'; echo PHP_EOL; \$id=(new AIOL_Client(\$cr, new AIOL_Logger()))->identity(); echo is_wp_error(\$id)?'identity error':'identity org '.\$id['organization_id'];" 2>&1 | tail -2; echo
WID=$($W wc product create --user=admin --name="Toranjebin Grade A — 100 g" --type=simple --status=publish --regular_price=12.50 --sku=TRJ-A-100-R$RANDOM --manage_stock=true --stock_quantity=40 --porcelain 2>&1 | tail -1); echo "$WID" > woo_id.txt; echo "woo product $WID"
$W post meta update $WID _aiol_object_id $CPID >/dev/null; $W post meta update $WID _aiol_object_type product >/dev/null
$W post update $WID --post_excerpt="Lab-tested Persian manna" >/dev/null 2>&1
echo "content mapping: $($W post meta get $WID _aiol_sync_state)"
$W eval "\$cl=new AIOL_Client(new AIOL_Credentials(), new AIOL_Logger()); \$r=\$cl->upsert_commerce_mapping('$CPID', $WID, null, get_post_meta($WID,'_sku',true)); if(is_wp_error(\$r)){echo 'error '.\$r->get_error_message();}else{\$mid=\$r['mapping']['id']??(\$r['id']??''); update_post_meta($WID,'_aiol_commerce_mapping_id',\$mid); echo 'commerce mapping '.\$mid;}" 2>&1 | tail -1; echo
$W wc product update $WID --user=admin --regular_price=12.90 >/dev/null 2>&1
echo "price sync: $($W post meta get $WID _aiol_commerce_sync_state)"
$W wc product update $WID --user=admin --stock_quantity=7 >/dev/null 2>&1
echo "stock sync: $($W post meta get $WID _aiol_commerce_sync_state)"
