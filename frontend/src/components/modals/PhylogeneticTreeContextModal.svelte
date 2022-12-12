<script  >

    export let params;
    import { getContext } from 'svelte';
    const context = getContext('app');
    let { controller, eventbus } = context.app();
    import getStores from '/utils/store';
    import LoadingAnimation from '/components/utils/LoadingAnimation.svelte';
    let showLoadingAnimation = false;
    import { newick_formatting } from "/utils/newick.js";
    import { Draw_Phylo } from "/utils/phylogenetic_tree.js";


    let samples_list = controller.config.samples;
    let samples = controller.config.samples;
    let number_of_sample = samples.length;
    let select_sample = [];
    let highlighted_sample = [];
    let newick = null;



function draw_graph() {

  
     showLoadingAnimation = true;


     const rightPlotMethod = document.getElementById("rightPlotMethod").value;
     select_sample = rightPlotMethod.split(',');
     const highlighted = document.getElementById("highlighted").value;
     highlighted_sample = highlighted.split(',');

     params['number_of_sample'] = select_sample.length;
     params['select_sample'] = select_sample;

     controller.phylogenetic(params, _result => {

        newick  = newick_formatting(_result.phylogenetic_result)
        showLoadingAnimation = false;
        var my_width = _result.number_of_sample * 20

        var my_height = _result.number_of_sample * 40

        const myNode = document.getElementById("phylogenetic_graph");
        myNode.textContent = '';

        Draw_Phylo('#phylogenetic_graph', newick, {
            width: my_width,
            height: my_height,
            select_element: highlighted_sample
        }); 

    }); 

}


</script>


<div>
<div class="divbrowse-modal-dialogue-headline">Phylogenetic tree</div>


<div class="clearfix">

    <!--
        <div style="float: left;">
            <label style="margin-left: 30px;">Number of Sample select : </label>
            <input bind:value={number_of_sample} type="number" id="number_of_sample" class="divbrowse-form-control" style="width: 40px;height: 30px; padding: 0 8px;">
        </div>
    -->

        <div style="float: left;">
            <label style="margin-left: 30px;">Select the samples : </label>
            <textarea  class="divbrowse-form-control" style="float:right; margin-left: 10px;"  id="rightPlotMethod"   bind:value={samples_list}   rows="20" cols="250"></textarea>

        </div>

        {#if showLoadingAnimation}
        <div style="float:left;margin-left:20px;">
            <LoadingAnimation size="small" />
        </div>
        {/if}




        <div style="float: left;">

            <div style="float: left;">
                <label style="margin-left: 30px;">Highlighted the samples name : </label>
            </div>
            <textarea  class="divbrowse-form-control" style="float:right; margin-left: 10px;"  id="highlighted"   rows="7" cols="250"></textarea>

        </div>
        <button on:click={draw_graph} type="button" class="divbrowse-btn divbrowse-btn-light" style="float: left;">draw graph</button>
       
        <div id="phylogenetic_graph">

        </div>

</div>

</div>

<style >
#phylogenetic_graph {
 
  margin-top: 100px;
  margin-right: 100px;
  margin-left: 20px;
  margin-bottom: 20px;

  padding: 110px 50px 50px 110px;
}

</style>