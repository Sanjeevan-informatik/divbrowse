<script>
export let data;

import getStores from '/utils/store';
const { variantWidth } = getStores();

import { getContext } from 'svelte';

const context = getContext('app');
let { appId } = context.app();

import { scaleLinear } from "d3-scale";

import { delegate } from 'tippy.js';

let scale = scaleLinear().domain([0, 0.1]).range([0, 1]);

const tippyProps = {
    delay: 0,
    target: 'div#'+appId+' span.het-indicator',
    animation: false,
    placement: "bottom",
    allowHTML: true
};


let hets;
let tippyInstancesMaf;

$: {
    hets = data.per_variant_stats.heterozygosity_freq;

    scale = scaleLinear().domain([0, Math.max(...hets) ]).range([0, 1]);
    
    if (tippyInstancesMaf !== undefined && typeof tippyInstancesMaf[0].destroy === "function") { tippyInstancesMaf[0].destroy(); }
    tippyInstancesMaf = delegate('body', tippyProps);
}

</script>


<div class="track heterozygous-calls-freq" style="height: 20px;"><div class="label">Heterozygosity indicator</div>
    {#each hets as het, i}
    <span class="variant-hover het-indicator" data-tippy-content="HET = {(het).toFixed(3)}" data-position="{data.variants_coordinates[i]}" style="background-color: rgba(255, 136, 71, { scale(het) }); width: {$variantWidth}px;">&nbsp;</span>
    {/each}
</div>


<style>

:global(.tippy-box) {
    font-family: sans-serif;
}

:global(.tippy-content) {
    font-size: 0.85rem;
    font-family: sans-serif;
}

:global(.tippy-tooltip[data-out-of-boundaries]) {
  opacity: 0;
}

</style>