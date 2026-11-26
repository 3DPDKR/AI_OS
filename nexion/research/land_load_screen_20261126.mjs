// NEXION static tripod ground-reaction and hip moment screen; SI units.
// Run: node land_load_screen_20261126.mjs
function research(){
  // Offline point contact screening, SI units. No hardware control.
  const g=9.80665,rad=Math.PI/180,eps=1e-9;
  const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const add=(a,b)=>a.map((x,i)=>x+b[i]),sub=(a,b)=>a.map((x,i)=>x-b[i]),scale=(a,s)=>a.map(x=>x*s),norm=a=>Math.hypot(...a);
  function model({mass=2,R=.12,H=.075,hipR=.06,hipH=.065,offset=[0,0],slope=0,heading=0,mu=.4,reserve=.02,group=0}={}){
    if(!Array.isArray(offset)||offset.length!==2||![mass,R,H,hipR,hipH,...offset,slope,heading,mu,reserve].every(Number.isFinite)||mass<=0||R<=0||H<0||hipR<0||hipR>R||hipH<0||slope<0||slope>=90||mu<0||reserve<0||![0,1].includes(group))throw new RangeError("invalid input");
    const theta=slope*rad,d=[Math.cos(heading*rad),Math.sin(heading*rad)],down=H*Math.tan(theta);
    const p=[offset[0]+down*d[0],offset[1]+down*d[1],0],com=[...offset,H];
    const weight=[mass*g*Math.sin(theta)*d[0],mass*g*Math.sin(theta)*d[1],-mass*g*Math.cos(theta)];
    const feet=Array.from({length:3},(_,i)=>{const a=(group+2*i)*Math.PI/3;const u=[Math.cos(a),Math.sin(a)];const point=[R*u[0],R*u[1],0],hip=[hipR*u[0],hipR*u[1],hipH];const lambda=(1+2*(p[0]*u[0]+p[1]*u[1])/R)/3;const F=scale(weight,-lambda);return {lambda,point,hip,F,normal:F[2],resultant:norm(F),hipMoment:norm(cross(sub(point,hip),F))};});
    const margin=1.5*R*Math.min(...feet.map(f=>f.lambda));
    const forceResidual=norm(feet.reduce((s,f)=>add(s,f.F),weight));
    const momentResidual=norm(feet.reduce((s,f)=>add(s,cross(sub(f.point,com),f.F)),[0,0,0]));
    return {feet,margin,forceResidual,momentResidual,pass:margin>eps&&margin>=reserve-eps&&mu-Math.tan(theta)>eps};
  }
  function sweep(mass,slope){
    let count=0,passed=0,minMargin=Infinity,peakNormal=0,peakMoment=0,peakShare=0,maxForceResidual=0,maxMomentResidual=0;
    for(let group=0;group<2;group++)for(let h=0;h<360;h+=10)for(let a=0;a<360;a+=10){
      const r=model({mass,slope,heading:h,offset:[.015*Math.cos(a*rad),.015*Math.sin(a*rad)],group});
      count++;passed+=Number(r.pass);minMargin=Math.min(minMargin,r.margin);
      maxForceResidual=Math.max(maxForceResidual,r.forceResidual);maxMomentResidual=Math.max(maxMomentResidual,r.momentResidual);
      if(r.pass){peakNormal=Math.max(peakNormal,...r.feet.map(f=>f.normal));peakMoment=Math.max(peakMoment,...r.feet.map(f=>f.hipMoment));peakShare=Math.max(peakShare,...r.feet.map(f=>f.lambda));}
    }
    return {mass,slope,count,passed,minMargin,peakNormal:passed?peakNormal:null,peakMoment:passed?peakMoment:null,peakShare:passed?peakShare:null,maxForceResidual,maxMomentResidual};
  }
  function run(){
    let checks=0;const check=(s,c)=>{if(!c)throw Error(s);checks++},eq=(a,b)=>Math.abs(a-b)<1e-8;
    const flat=model();check("equal normal load",flat.feet.every(f=>eq(f.normal,2*g/3)));
    check("flat moment",flat.feet.every(f=>eq(f.hipMoment,.06*2*g/3)));
    check("flat margin",eq(flat.margin,.06));check("flat pass",flat.pass);
    const edge=model({offset:[-.06,0],reserve:0});check("edge contact fails",!edge.pass&&Math.abs(edge.margin)<eps);
    const outside=model({offset:[-.07,0]});check("no tensile contact",!outside.pass&&outside.feet.some(f=>f.normal<0));
    check("friction fail",!model({slope:25,H:0}).pass);
    check("reserve fail",!model({offset:[-.05,0]}).pass);
    check("double mass double moment",eq(model({mass:4}).feet[0].hipMoment,flat.feet[0].hipMoment*2));
    check("orientation B",eq(model({group:1}).feet[0].normal,flat.feet[0].normal));
    for(const v of [{mass:0},{R:0},{hipR:.13},{slope:90},{offset:[NaN,0]},{group:2},{mu:-1}]){let rejected=false;try{model(v)}catch(e){rejected=e instanceof RangeError}check("invalid "+JSON.stringify(v),rejected)}
    const rows=[1.5,2,2.5].flatMap(m=>[0,5,10,15,20,25,30].map(s=>sweep(m,s)));
    for(const r of rows){
      check("force equilibrium "+r.mass+"/"+r.slope,r.maxForceResidual<1e-9);
      check("moment equilibrium "+r.mass+"/"+r.slope,r.maxMomentResidual<1e-9);
      check("previous geometric bound "+r.mass+"/"+r.slope,eq(r.minMargin,.06-.015-.075*Math.tan(r.slope*rad)));
      check("previous pass count "+r.mass+"/"+r.slope,r.passed===[2592,2592,2592,2592,2454,0,0][r.slope/5]);
      if(r.passed===r.count)check("analytic peak load fraction "+r.mass+"/"+r.slope,eq(r.peakShare,(1+2*(.015+.075*Math.tan(r.slope*rad))/.12)/3));
    }
    return {checks,rows};
  }
  const result=run();for(let i=0;i<2;i++)if(JSON.stringify(run())!==JSON.stringify(result))throw Error("nondeterministic");return {repetitions:3,...result};
}
console.log(JSON.stringify(research(),null,2));
