// NEXION offline geometric screening; no actuator or network API.
// Units: mm, degrees. Run: node land_static_screen_20261125.mjs
function screen({radius=120,height=75,offset=[0,0],slope=0,heading=0,mu=0.4,feet=[0,2,4],reserve=20}={}){
  if(![radius,height,slope,heading,mu,reserve,...offset].every(Number.isFinite)||radius<=0||height<0||slope<0||slope>=90||mu<0||reserve<0||offset.length!==2||!Array.isArray(feet)||new Set(feet).size!==feet.length||feet.some(i=>!Number.isInteger(i)||i<0||i>5))throw new RangeError("invalid input");
  const rad=Math.PI/180,shift=height*Math.tan(slope*rad);
  const p=[offset[0]+shift*Math.cos(heading*rad),offset[1]+shift*Math.sin(heading*rad)];
  // A subset of the vertices of a regular convex hexagon is convex in angular order.
  const v=[...feet].sort((a,b)=>a-b).map(i=>[radius*Math.cos(i*Math.PI/3),radius*Math.sin(i*Math.PI/3)]);
  const frictionReserve=mu-Math.tan(slope*rad);
  if(v.length<3)return {margin:null,frictionReserve,pass:false};
  const margin=Math.min(...v.map((a,i)=>{const b=v[(i+1)%v.length],dx=b[0]-a[0],dy=b[1]-a[1];return (dx*(p[1]-a[1])-dy*(p[0]-a[0]))/Math.hypot(dx,dy);}));
  // Signed minimum supporting-line distance, not Euclidean exterior distance.
  return {margin,frictionReserve,pass:margin>1e-9&&margin>=reserve-1e-9&&frictionReserve>1e-9};
}
function sweep(slope){
  let worst=Infinity,passed=0,total=0;
  for(const feet of [[0,2,4],[1,3,5]])for(let h=0;h<360;h+=10)for(let a=0;a<360;a+=10){
    const r=screen({slope,heading:h,offset:[15*Math.cos(a*Math.PI/180),15*Math.sin(a*Math.PI/180)],feet});
    worst=Math.min(worst,r.margin);passed+=Number(r.pass);total++;
  }
  return {slope,worst,bound:60-15-75*Math.tan(slope*Math.PI/180),passed,total};
}
function run(){
  const checks=[];
  const check=(label,condition)=>{if(!condition)throw Error(label);checks.push(label);};
  const eq=(a,b)=>Math.abs(a-b)<1e-8;
  check("flat tripod A",eq(screen().margin,60));
  check("flat tripod B",eq(screen({feet:[1,3,5]}).margin,60));
  check("six foot rest",eq(screen({feet:[0,1,2,3,4,5]}).margin,120*Math.sqrt(3)/2));
  check("offset reduces margin",eq(screen({offset:[7.5,15*Math.sqrt(3)/2]}).margin,45));
  check("two feet fail",screen({feet:[0,2]}).pass===false&&screen({feet:[0,2]}).margin===null);
  check("outside support fails",screen({offset:[100,100]}).margin<0&&!screen({offset:[100,100]}).pass);
  check("zero friction reserve fails",!screen({slope:0,mu:0}).pass);
  check("slip despite support",screen({slope:25,height:0}).margin>20&&!screen({slope:25,height:0}).pass);
  check("positive but insufficient design reserve",screen({offset:[25,25*Math.sqrt(3)]}).margin>0&&!screen({offset:[25,25*Math.sqrt(3)]}).pass);
  for(const input of [{radius:0},{slope:90},{feet:[0,0,2]},{offset:[NaN,0]}]){
    let rejected=false;try{screen(input);}catch(e){rejected=e instanceof RangeError;}check("reject "+JSON.stringify(input),rejected);
  }
  const rows=[0,5,10,15,20,25,30].map(sweep);
  for(const r of rows)check("analytic worst bound "+r.slope,eq(r.worst,r.bound));
  check("5-degree all pass",rows[1].passed===rows[1].total);
  check("20-degree not all pass",rows[4].passed<rows[4].total);
  check("25-degree no pass",rows[5].passed===0);
  const restAfterFault=screen({slope:5,heading:60,offset:[7.5,15*Math.sqrt(3)/2],feet:[1,2,3,4,5]});
  check("five-foot static rest after one missing foot",restAfterFault.pass);
  return {checks:checks.length,rows,restAfterFault};
}
const results=run();
if(JSON.stringify(run())!==JSON.stringify(results)||JSON.stringify(run())!==JSON.stringify(results))throw Error('nondeterministic');
console.log(JSON.stringify({repetitions:3,...results},null,2));
