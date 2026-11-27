// NEXION offline three-axis leg geometry and static contact torque screening. SI units.
// Node.js: node land_joint_screen_20261127.mjs
// No hardware I/O; no dynamic, link gravity, collision, fatigue, or thermal model.
function research(){
 const D=Math.PI/180,g=9.80665,L1=.045,L2=.065,R=.12,H=.075,hipR=.06,hipH=.065;
 const dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0),sub=(a,b)=>a.map((x,i)=>x-b[i]),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]],norm=a=>Math.hypot(...a);
 function fk(q){
  const [y,p,k]=q, r=L1*Math.cos(p)+L2*Math.cos(p+k),z=L1*Math.sin(p)+L2*Math.sin(p+k);
  return [r*Math.cos(y),r*Math.sin(y),z];
 }
 function ik(v){
  if(v.length!==3||!v.every(Number.isFinite))return null;
  const [x,y,z]=v,r=Math.hypot(x,y),c=(r*r+z*z-L1*L1-L2*L2)/(2*L1*L2);
  if(r<1e-9||c<=-1+1e-10||c>=1-1e-10)return null;
  const k=-Math.acos(c),p=Math.atan2(z,r)-Math.atan2(L2*Math.sin(k),L1+L2*c),q=[Math.atan2(y,x),p,k];
  return q.every((v,i)=>v>=[-45,-75,-150][i]*D&&v<=[45,60,-15][i]*D)?q:null;
 }
 function jac(q){
  const [y,p,k]=q,[x,Y,z]=fk(q),r=Math.hypot(x,Y),s=L2*Math.sin(p+k),c=L2*Math.cos(p+k);
  return [[-Y,x,0],[-z*Math.cos(y),-z*Math.sin(y),r],[-s*Math.cos(y),-s*Math.sin(y),c]];
 }
 const q0=ik([R-hipR,0,-hipH]);
 if(!q0)throw Error("nominal infeasible");
 let checks=0;const check=(msg,cond)=>{if(!cond)throw Error(msg);checks++};
 const almost=(a,b,t=1e-8)=>Math.abs(a-b)<t;
 let workspace=0,reachable=0,maxFkError=0,maxJacError=0;
 for(let x=40;x<=80;x+=5)for(let y=-20;y<=20;y+=5)for(let z=-75;z<=-40;z+=5){
  workspace++;const v=[x,y,z].map(a=>a/1000),q=ik(v);if(!q)continue;reachable++;
  const e=norm(sub(fk(q),v));maxFkError=Math.max(maxFkError,e);check("IK round trip",e<1e-10);
  const J=jac(q),h=1e-6;
  for(let j=0;j<3;j++){
   const a=q.slice(),b=q.slice();a[j]+=h;b[j]-=h;const finite=sub(fk(a),fk(b)).map(x=>x/(2*h));
   const error=norm(sub(finite,J[j]));maxJacError=Math.max(maxJacError,error);check("Jacobian finite difference",error<1e-8);
  }
 }
 check("workspace nonempty and rejects some",reachable>0&&reachable<workspace);
 for(const v of [[0,0,0],[.2,0,0],[.11,0,0],[.02,0,0],[NaN,0,0],[0,.06,-.065]])check("unreachable or outside limits",ik(v)===null);
 const J=jac(q0),foot=fk(q0),knee=[L1*Math.cos(q0[1]),0,L1*Math.sin(q0[1])];
 const rows=[];let maxProjectionError=0,maxVirtualWorkError=0;
 for(const mass of [1.5,2,2.5])for(const slope of [0,5,10,15,20,25,30]){
  const t=slope*D;let count=0,passed=0,peak=[0,0,0],peakHipNorm=0;
  for(let group=0;group<2;group++)for(let h=0;h<360;h+=10)for(let a=0;a<360;a+=10){
   count++;const heading=h*D,off=a*D,proj=[.015*Math.cos(off)+H*Math.tan(t)*Math.cos(heading),.015*Math.sin(off)+H*Math.tan(t)*Math.sin(heading)];
   const legs=Array.from({length:3},(_,i)=>{const phi=(group+2*i)*Math.PI/3,lam=(1+2*(proj[0]*Math.cos(phi)+proj[1]*Math.sin(phi))/R)/3;
   return {lam,F:[-lam*mass*g*Math.sin(t)*Math.cos(heading-phi),-lam*mass*g*Math.sin(t)*Math.sin(heading-phi),lam*mass*g*Math.cos(t)]}});
   if(1.5*R*Math.min(...legs.map(l=>l.lam))<.02-1e-9||.4-Math.tan(t)<=1e-9)continue;
   passed++;
   for(const {F} of legs){
    const tau=J.map(col=>dot(col,F)),M=cross(foot,F),Mk=cross(sub(foot,knee),F);
    const independent=[M[2],-M[1],-Mk[1]],err=norm(sub(tau,independent));
    maxProjectionError=Math.max(maxProjectionError,err);
    const qdot=[.3,-.2,.4],vel=[0,1,2].map(i=>J.reduce((s,col,j)=>s+col[i]*qdot[j],0));
    maxVirtualWorkError=Math.max(maxVirtualWorkError,Math.abs(dot(tau,qdot)-dot(F,vel)));
    for(let j=0;j<3;j++)peak[j]=Math.max(peak[j],Math.abs(tau[j]));
    peakHipNorm=Math.max(peakHipNorm,norm(M));
   }
  }
  check("previous static pass count",passed===[2592,2592,2592,2592,2454,0,0][slope/5]);
  rows.push({mass,slope,count,passed,peak:passed?peak:null,peakHipNorm:passed?peakHipNorm:null});
 }
 check("independent moment projection",maxProjectionError<1e-10);check("virtual work",maxVirtualWorkError<1e-10);
 check("flat yaw zero",rows.find(r=>r.mass===2&&r.slope===0).peak[0]<1e-10);
 const r=rows.find(r=>r.mass===2&&r.slope===5);
 check("prior hip norm agrees to 0.001 Nm",Math.abs(r.peakHipNorm-.493)<.0005);
 const half=rows.find(r=>r.mass===1.5&&r.slope===5),large=rows.find(r=>r.mass===2.5&&r.slope===5);
 check("mass scaling",r.peak.every((v,i)=>almost(half.peak[i]/1.5,v/2)&&almost(large.peak[i]/2.5,v/2)));
 return {checks,workspace,reachable,maxFkError,maxJacError,maxProjectionError,maxVirtualWorkError,nominalAnglesDeg:q0.map(x=>x/D),rows};
}
const result=research();for(let i=0;i<2;i++)if(JSON.stringify(research())!==JSON.stringify(result))throw Error('repeat mismatch');
console.log(JSON.stringify({repetitions:3,...result},null,2));
