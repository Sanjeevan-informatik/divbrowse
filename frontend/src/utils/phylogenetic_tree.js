function rightAngleDiagonal () {
  var projection = function(d) { return [d.y, d.x]; }
  
  var path = function(pathData) {
    return "M" + pathData[0] + ' ' + pathData[1] + " " + pathData[2];
  }
  
  function diagonal(diagonalPath, i) {
    var source = diagonalPath.source,
        target = diagonalPath.target,
        midpointX = (source.x + target.x) / 2,
        midpointY = (source.y + target.y) / 2,
        pathData = [source, {x: target.x, y: source.y}, target];
    pathData = pathData.map(projection);
    return path(pathData)
  }
  
  diagonal.projection = function(x) {
    if (!arguments.length) return projection;
    projection = x;
    return diagonal;
  };
  
  diagonal.path = function(x) {
    if (!arguments.length) return path;
    path = x;
    return diagonal;
  };
  
  return diagonal;
}


function scaleBranchLengths(nodes, w) {
  // Visit all nodes and adjust y pos width distance metric
  var visitPreOrder = function(root, callback) {
    callback(root)
    if (root.children) {
      for (var i = root.children.length - 1; i >= 0; i--){
        visitPreOrder(root.children[i], callback)
      };
    }
  }
  visitPreOrder(nodes[0], function(node) {
    node.rootDist = (node.parent ? node.parent.rootDist : 0) + (node.length || 0)
  })
  var rootDists = nodes.map(function(n) { return n.rootDist; });
  var yscale = d3.scale.linear()
    .domain([0, d3.max(rootDists)])
    .range([0, w]);
  visitPreOrder(nodes[0], function(node) {
    node.y = yscale(node.rootDist)
  })
  return yscale
}

function Draw_Phylo(selector, nodes, options) {
  options = options || {}
  let  w = options.width || d3.select(selector).style('width') || d3.select(selector).attr('width')
  let h = options.height || d3.select(selector).style('height') || d3.select(selector).attr('height')
    w = parseInt(w),
    h = parseInt(h);
let tree = options.tree || d3.layout.cluster()
  .size([h, w])
  .sort(function(node) { return node.children ? node.children.length : -1; })
  .children(options.children || function(node) {
    return node.branchset
  });
let diagonal = options.diagonal || rightAngleDiagonal();
let svg =  d3.select(selector).append("svg:svg")
    .attr("width", w + 500)
    .attr("height", h + 30)
  .append("svg:g")
    .attr("transform", "translate(20, 20)");
 nodes = tree(nodes);


let yscale = scaleBranchLengths(nodes, w)
        
svg.append("style").text(`

.link--active {
  stroke: #000 !important;
  stroke-width: 1.5px;
}

.link-extension--active {
  stroke-opacity: .6;
}

.label--active {
  font-weight: bold;
  fill : green;
  font-size : 20px;

}

.label--mark {
  font-weight: normal;
}

.label--highlight {
  font-weight: bold;
  fill : green;
  font-size : 20px;
}

`);

let link = svg.selectAll("path.link")
.data(tree.links(nodes))
.enter().append("svg:path")
.attr("class", "link")
.attr("d", diagonal)
.attr("fill", "none")
.attr("stroke", "#000000")
.attr("stroke-width", "0.5px");

let node = svg.selectAll("g.node")
  .data(nodes)
.enter().append("svg:g")
  .attr("class", function(n) {
    if (n.children) {
      if (n.depth == 0) {
        return "root node"
      } else {
        return "inner node"
      }
    } else {
      return "leaf node"
    }
  })
  .attr("transform", function(d) { return "translate(" + d.y + "," + d.x + ")"; })
  .on("mouseover", mouseovered(true))
  .on("mouseout", mouseovered(false));
  



  svg.selectAll('g.inner.node')
    .append("svg:text")
      .attr("dx", -4)
      .attr("dy", -6)
      .attr("text-anchor", 'end')
      .attr('font-size', '10px')
      .attr('fill', '#000000')
      .text(function(d) { return d.length; });

  svg.selectAll('g.leaf.node').append("svg:text")
    .attr("dx", 8)
    .attr("dy", 3)
    .attr("text-anchor", "start")
    .attr('font-family', 'Helvetica Neue, Helvetica, sans-serif')
    .attr('font-size', '10px')
    .attr('fill', 'black')
    .text(function(d) { return d.name + ' ('+d.length+')'; })
    .attr("my" , select(options.select_element, true));

return {svg: svg}
}

function mouseovered(active) {
  return function() {   
    d3.select(this).classed("label--active", active);
    /*
    console.log(d3.select(this)._groups[0][0].__data__.name == "BRIDGE_WGS_HOR_1048")
    console.log(d3.selectAll('g.leaf.node')._groups[0])
    console.log(d3.selectAll('g.leaf.node')._groups[0][0].__data__.name == "BRIDGE_WGS_HOR_1048")
    */   
  };
}

function select(select_element ,activate) {

  return function() {

    var node = d3.selectAll('g.leaf.node')._groups[0]

    for (var j=0;j<select_element.length;j++)
    {
      for (var i=0;i<node.length;i++)
      {
            if(node[i].__data__.name == select_element[j]) {
              node[i].classList.add("label--highlight");
            } 
      }  
    }


};
}
export { Draw_Phylo } ;